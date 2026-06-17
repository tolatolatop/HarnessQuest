import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AgentCase, AgentSession, AIAnalysis, AIAnalysisStatus

ANALYSIS_SYSTEM_PROMPT = """You are an AI workflow incident analyst.
Return strict JSON only. Analyze the AI agent session and case evidence.
Do not assign final responsibility; provide suggestions for human review."""


def _compact_session(session: AgentSession | None) -> dict[str, Any]:
    if not session:
        return {}
    return {
        "agent_type": session.agent_type,
        "repository": session.repository,
        "branch": session.branch,
        "commit_sha": session.commit_sha,
        "summary": session.summary,
        "metadata": session.metadata_json,
        "raw_artifact_uri": session.raw_artifact_uri,
        "langfuse_trace_id": session.langfuse_trace_id,
        "langfuse_url": session.langfuse_url,
    }


def run_case_analysis(case_id: str) -> None:
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        case = db.get(AgentCase, case_id)
        if not case:
            return
        case.ai_analysis_status = AIAnalysisStatus.running
        db.commit()
        analysis = _perform_analysis(db, case)
        case.ai_analysis_status = AIAnalysisStatus.succeeded if not analysis.error_message else AIAnalysisStatus.failed
        db.commit()
    finally:
        db.close()


def _perform_analysis(db: Session, case: AgentCase) -> AIAnalysis:
    settings = get_settings()
    evidence = {
        "case": {
            "title": case.title,
            "source": case.source.value,
            "status": case.status.value,
            "severity": case.severity.value,
            "problem_type": case.problem_type,
            "human_conclusion": case.human_conclusion,
            "handling_action": case.handling_action,
        },
        "session": _compact_session(case.session),
    }
    analysis = AIAnalysis(case_id=case.id, model=settings.analyzer_model, input_artifact_refs=evidence)
    db.add(analysis)
    db.flush()

    if not settings.analyzer_base_url or not settings.analyzer_api_key:
        analysis.summary = "Analyzer is not configured. Set ANALYZER_BASE_URL and ANALYZER_API_KEY."
        analysis.ownership_suggestion = "unknown"
        analysis.severity_suggestion = case.severity.value
        analysis.next_steps = ["Configure an OpenAI-compatible analyzer model.", "Review this case manually."]
        analysis.confidence = 0.0
        return analysis

    try:
        result = _call_analyzer(evidence)
        analysis.summary = result.get("summary")
        analysis.failure_point = result.get("failure_point")
        analysis.ownership_suggestion = result.get("ownership_suggestion")
        analysis.severity_suggestion = result.get("severity_suggestion")
        analysis.next_steps = result.get("next_steps") or []
        analysis.experience_suggestion = result.get("experience_suggestion")
        analysis.confidence = result.get("confidence")
    except Exception as exc:  # noqa: BLE001
        analysis.error_message = str(exc)
        analysis.summary = "AI analysis failed. Review the case manually."
        analysis.ownership_suggestion = "unknown"
        analysis.next_steps = [
            "Check analyzer configuration and raw evidence.",
            "Retry analysis after fixing the issue.",
        ]
    return analysis


def _call_analyzer(evidence: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    schema_hint = {
        "summary": "what happened",
        "failure_point": "likely failure point",
        "ownership_suggestion": (
            "model_behavior_issue | tooling_issue | user_prompt_issue | project_configuration_issue | "
            "codebase_issue | workflow_process_issue | security_permission_issue | unknown"
        ),
        "severity_suggestion": "low | medium | high | critical",
        "next_steps": ["recommended next step"],
        "experience_suggestion": "what reusable knowledge can be extracted",
        "confidence": 0.0,
    }
    body = {
        "model": settings.analyzer_model,
        "messages": [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"required_json_shape": schema_hint, "evidence": evidence},
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=settings.analyzer_timeout_seconds) as client:
        response = client.post(
            f"{str(settings.analyzer_base_url).rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.analyzer_api_key}"},
            json=body,
        )
        response.raise_for_status()
    response_body = response.json()
    if not isinstance(response_body, dict):
        raise ValueError("Analyzer response must be a JSON object")
    content = response_body["choices"][0]["message"]["content"]
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError("Analyzer content must be a JSON object")
    return result
