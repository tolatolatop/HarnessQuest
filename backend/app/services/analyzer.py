import json
from typing import Any

import httpx
from jinja2 import Environment
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AgentCase, AgentSession, AIAnalysis, AIAnalysisStatus

ANALYSIS_SYSTEM_PROMPT = """You are an AI workflow incident analyst.
Return strict JSON only. Analyze the AI agent session and case evidence.
Do not assign final responsibility; provide suggestions for human review."""

ANALYSIS_INPUT_TEMPLATE_VERSION = "markdown-compact-v1"
MAX_TEXT_CHARS = 800
MAX_TOOL_CHARS = 300
MAX_CONVERSATION_ITEMS = 40
MAX_RENDERED_INPUT_CHARS = 12_000

ANALYSIS_INPUT_TEMPLATE = """# AI 工单分析输入

## 工单
标题：{{ case.title }}
状态：{{ case.status }}
严重级别：{{ case.severity }}
问题类型：{{ case.problem_type }}
{% if case.scene_description %}
场景：{{ case.scene_description }}
{% endif %}
{% if case.expected_result %}
预期：{{ case.expected_result }}
{% endif %}
{% if case.actual_result %}
实际：{{ case.actual_result }}
{% endif %}
{% if case.reproducible is not none %}
可复现：{{ "是" if case.reproducible else "否" }}
{% endif %}
{% if case.feedback_reporter %}
反馈人：{{ case.feedback_reporter }}
{% endif %}
{% if case.responsible_owner %}
责任人：{{ case.responsible_owner }}
{% endif %}

## 会话
Agent：{{ session.agent_type }}
仓库：{{ session.repository or "-" }}
分支：{{ session.branch or "-" }}
摘要：{{ session.summary or "-" }}

## 对话历史
{% for item in conversation %}
### {{ item.label }}
{{ item.content }}
{% endfor %}

## 关键证据
{% if evidence.files_changed %}
修改文件：
{% for path in evidence.files_changed %}
- {{ path }}
{% endfor %}
{% endif %}
{% if evidence.tool_errors %}
工具错误：
{% for err in evidence.tool_errors %}
- {{ err }}
{% endfor %}
{% endif %}
{% if evidence.notable_events %}
重要事件：
{% for event in evidence.notable_events %}
- {{ event }}
{% endfor %}
{% endif %}

## 请输出 JSON
{
  "summary": "发生了什么",
  "failure_point": "可能的问题点",
  "ownership_suggestion": "model_behavior_issue | tooling_issue | user_prompt_issue | project_configuration_issue | codebase_issue | workflow_process_issue | security_permission_issue | unknown",
  "severity_suggestion": "low | medium | high | critical",
  "next_steps": ["下一步建议"],
  "experience_suggestion": "可沉淀的经验",
  "confidence": 0.0
}
"""

_TEMPLATE_ENV = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)


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


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float | bool):
        return str(value)
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _truncate(value: Any, limit: int) -> str:
    text = (_text(value) or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}... [已截断 {len(text) - limit} 字符]"


def _metadata_list(metadata: dict[str, Any], key: str) -> list[Any]:
    value = metadata.get(key)
    return value if isinstance(value, list) else []


def _tool_content_summary(value: Any) -> str:
    text = (_text(value) or "").strip()
    if not text:
        return "工具已调用，未捕获输出。"
    if "Output too large" in text or "输出过大" in text:
        return "工具输出过大，完整输出已省略。"
    return f"工具已调用，完整输入输出未送入模型（原始 {len(text)} 字符）。"


def _conversation_items(session: AgentSession | None) -> list[dict[str, str]]:
    if not session:
        return []
    metadata = session.metadata_json or {}
    raw_items = _metadata_list(metadata, "conversation") or _metadata_list(metadata, "messages")
    items: list[dict[str, str]] = []
    skipped_thinking = 0
    omitted = 0

    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        role = _truncate(raw.get("role") or raw.get("type") or "observation", 32).lower()
        if role == "thinking":
            skipped_thinking += 1
            continue
        title = _truncate(raw.get("title") or raw.get("name") or role, 80)
        content = raw.get("content") or raw.get("message") or raw.get("text") or raw
        if role in {"tool", "shell", "file", "function", "mcp", "skill"}:
            label = f"工具：{title}"
            body = _tool_content_summary(content)
        elif role == "user":
            label = "用户"
            body = _truncate(content, MAX_TEXT_CHARS)
        elif role == "assistant":
            label = "助手"
            body = _truncate(content, MAX_TEXT_CHARS)
        else:
            label = title or role
            body = _truncate(content, MAX_TOOL_CHARS)
        if body:
            items.append({"label": label, "content": body})

    if not items:
        user_input = _truncate(metadata.get("user_input"), MAX_TEXT_CHARS)
        assistant_output = _truncate(metadata.get("assistant_output"), MAX_TEXT_CHARS)
        if user_input:
            items.append({"label": "用户", "content": user_input})
        if assistant_output:
            items.append({"label": "助手", "content": assistant_output})

    if len(items) > MAX_CONVERSATION_ITEMS:
        omitted = len(items) - MAX_CONVERSATION_ITEMS
        head_count = MAX_CONVERSATION_ITEMS // 2
        tail_count = MAX_CONVERSATION_ITEMS - head_count
        items = [
            *items[:head_count],
            {"label": "系统", "content": f"中间 {omitted} 条对话已省略，仅保留开头和结尾。"},
            *items[-tail_count:],
        ]
    if skipped_thinking:
        items.append({"label": "系统", "content": f"已过滤 {skipped_thinking} 条 thinking 内容。"})
    return items


def _input_path(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("path", "file_path", "filePath"):
        text = _text(value.get(key))
        if text:
            return text
    return None


def _compact_evidence(session: AgentSession | None) -> dict[str, list[str]]:
    if not session:
        return {"files_changed": [], "tool_errors": [], "notable_events": []}
    metadata = session.metadata_json or {}
    files_changed: list[str] = []
    tool_errors: list[str] = []
    notable_events: list[str] = []

    for edit in _metadata_list(metadata, "file_edits"):
        if isinstance(edit, dict):
            path = _input_path(edit) or _text(edit.get("path"))
            if path and path not in files_changed:
                files_changed.append(path)

    for err in _metadata_list(metadata, "errors"):
        if isinstance(err, dict):
            message = _truncate(err.get("message") or err, MAX_TOOL_CHARS)
        else:
            message = _truncate(err, MAX_TOOL_CHARS)
        if message:
            tool_errors.append(message)

    for command in _metadata_list(metadata, "shell_commands"):
        if not isinstance(command, dict):
            continue
        output = _text(command.get("output")) or ""
        if len(output) > MAX_TOOL_CHARS:
            command_text = _truncate(command.get("command"), 120)
            notable_events.append(f"命令输出较长，已省略全文：{command_text}")
        if command.get("exit_code") not in {None, 0}:
            command_text = _truncate(command.get("command"), 120)
            notable_events.append(f"命令退出码非 0：{command_text}")

    if metadata.get("git_diff"):
        notable_events.append("会话包含 git diff，分析输入未包含完整 diff。")
    return {
        "files_changed": files_changed[:20],
        "tool_errors": tool_errors[:20],
        "notable_events": notable_events[:20],
    }


def _analysis_case(case: AgentCase) -> dict[str, Any]:
    return {
        "title": case.title,
        "source": case.source.value,
        "status": case.status.value,
        "severity": case.severity.value,
        "problem_type": case.problem_type,
        "scene_description": case.scene_description,
        "expected_result": case.expected_result,
        "actual_result": case.actual_result,
        "reproducible": case.reproducible,
        "feedback_reporter": case.feedback_reporter,
        "responsible_owner": case.responsible_owner,
        "human_conclusion": case.human_conclusion,
        "handling_action": case.handling_action,
    }


def _analysis_session(session: AgentSession | None) -> dict[str, Any]:
    if not session:
        return {"agent_type": "-", "repository": None, "branch": None, "summary": None}
    return {
        "agent_type": session.agent_type,
        "repository": session.repository,
        "branch": session.branch,
        "summary": session.summary,
        "raw_artifact_uri": session.raw_artifact_uri,
        "langfuse_trace_id": session.langfuse_trace_id,
        "langfuse_url": session.langfuse_url,
    }


def _build_analysis_input(case: AgentCase) -> dict[str, Any]:
    context = {
        "case": _analysis_case(case),
        "session": _analysis_session(case.session),
        "conversation": _conversation_items(case.session),
        "evidence": _compact_evidence(case.session),
    }
    rendered = _TEMPLATE_ENV.from_string(ANALYSIS_INPUT_TEMPLATE).render(**context).strip()
    if len(rendered) > MAX_RENDERED_INPUT_CHARS:
        rendered = f"{rendered[:MAX_RENDERED_INPUT_CHARS].rstrip()}\n\n[整体输入已截断]"
    return {
        "template_version": ANALYSIS_INPUT_TEMPLATE_VERSION,
        "context": context,
        "rendered_markdown": rendered,
        "rendered_chars": len(rendered),
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
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        _mark_analysis_failed(db, case_id, exc)
    finally:
        db.close()


def _mark_analysis_failed(db: Session, case_id: str, exc: Exception) -> None:
    settings = get_settings()
    message = str(exc) or exc.__class__.__name__
    analysis = AIAnalysis(
        case_id=case_id,
        model=settings.analyzer_model,
        summary="AI analysis failed before completion. Review the case manually.",
        ownership_suggestion="unknown",
        next_steps=[
            "Check analyzer worker logs and configuration.",
            "Retry analysis after fixing the recorded error.",
        ],
        error_message=message,
    )
    db.add(analysis)
    db.execute(
        update(AgentCase)
        .where(AgentCase.id == case_id)
        .values(ai_analysis_status=AIAnalysisStatus.failed)
    )
    db.commit()


def _perform_analysis(db: Session, case: AgentCase) -> AIAnalysis:
    settings = get_settings()
    analysis_input = _build_analysis_input(case)
    analysis = AIAnalysis(case_id=case.id, model=settings.analyzer_model, input_artifact_refs=analysis_input)
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
        result = _call_analyzer(str(analysis_input["rendered_markdown"]))
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


def _call_analyzer(analysis_input_markdown: str) -> dict[str, Any]:
    settings = get_settings()
    body = {
        "model": settings.analyzer_model,
        "messages": [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": analysis_input_markdown},
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
