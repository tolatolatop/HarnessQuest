# AI Agent Issue Loop Research and MVP Design

## Background

The team is beginning to build and operate complete AI workflows across a relatively large engineering group. Unlike traditional software systems, AI workflows are probabilistic, exploratory, and often lack mature domain design. Traditional ticket systems are proving insufficient because the core evidence is not a small deterministic log or a code diff, but a large, messy combination of conversation history, model output, tool calls, environment context, local command output, file edits, and human judgment.

The main pain points identified so far:

- AI-generated information is large and hard to review.
- Conversation and session context is difficult to preserve and navigate.
- Agent traces, tool calls, shell logs, and environment information are scattered.
- Practical experience does not reliably become reusable team knowledge.
- Resolved problems do not automatically become regression cases, guidance, or measurable quality improvements.
- Quality varies heavily by individual user skill and model choice.

The project direction is to build a system that helps teams collect AI agent usage records, analyze problems, assign ownership, close the loop, and extract reusable experience.

## Research Summary

The current LLMOps and AI observability ecosystem has converged around several core capabilities:

- Tracing and session management.
- Prompt and configuration versioning.
- Evaluation and scoring.
- Dataset and regression case management.
- Human review and annotation queues.
- Cost, latency, and quality monitoring.

Representative tools:

- Langfuse: open-source LLM engineering platform with tracing, sessions, prompt management, evaluations, datasets, and metrics.
- Arize Phoenix: OpenTelemetry-native AI observability and evaluation platform.
- Helicone: AI gateway and LLM observability, focused on provider routing, logging, cost, latency, and fallback.
- Agenta: prompt management, evaluation, observability, and SME collaboration.
- Opik: tracing, evaluation, monitoring, and optimization for LLM applications.
- Label Studio: structured human review, annotation workflows, rubrics, and audit trails.
- Promptfoo: LLM testing, red teaming, and CI regression evaluation.
- LiteLLM: multi-model proxy that can unify provider access, budgets, logging, and fallback.

The most important research conclusion is that Langfuse already covers much of the trace/session foundation. The missing layer is not another trace viewer. The missing layer is a productized issue-loop and operations workflow on top of AI agent usage records.

## Product Positioning

First-stage positioning:

> AI Agent usage issue-loop and analysis platform.

More concretely:

> Collect Claude Code, opencode, and similar AI agent sessions and logs; automatically analyze likely problem causes; support ownership assignment, workflow closure, metrics dashboards, and experience extraction.

The product should not be positioned as a complete AI workflow platform in the first stage. That scope is too large and would make early adoption harder. The first stage should focus on low-intrusion data collection and visible problem-loop value.

## Strategic Decision

Langfuse will be introduced as a foundational system for AI session and trace management.

However, the first stage will not force the team to adopt a unified model gateway or standardized AI usage flow. Because the team is large, a half-finished platform would be hard to promote broadly. The system should first collect real usage records with low disruption, even if the records are incomplete.

The initial approach:

- Deploy Langfuse as the session and trace base.
- Use open-source plugins, hooks, wrappers, or local collectors to collect offline agent usage records.
- Build an in-house issue-loop system on top of collected sessions and logs.
- Launch a frontend console and dashboard quickly.
- Demonstrate one clear innovation point: AI-assisted log/session analysis.

## First-Stage Goals

The first stage aims to prove product value and gather feedback, not to solve every LLMOps problem.

Goals:

- Collect real AI agent usage sessions with low user friction.
- Allow sessions/logs to be converted into trackable cases.
- Automatically analyze long sessions and logs into actionable summaries.
- Support ownership assignment, status flow, and closure.
- Provide basic dashboards for usage, issue distribution, and closure metrics.
- Extract at least some reusable team knowledge from closed cases.
- Use real data and visible dashboards to attract project attention and feedback.

Suggested success criteria:

- 5-10 seed users connected.
- At least one main agent path supported, such as Claude Code or opencode.
- 100+ real sessions collected.
- 20+ AI cases created.
- 10+ cases manually closed.
- 5+ reusable experience items extracted.
- At least one clear example where AI analysis reduces review or debugging time.

## Non-Goals For Stage One

The first stage explicitly does not aim to:

- Build another trace system.
- Replace Langfuse.
- Force all users through a unified AI gateway.
- Standardize all model usage.
- Implement complex model routing.
- Implement full evaluation infrastructure.
- Implement a complete knowledge base.
- Implement organization-wide prompt or recipe management.
- Guarantee complete trace capture.
- Roll out to all projects at once.

These capabilities can be considered in later stages after the issue-loop system proves value.

## Stage-One Scope

Stage one consists of five core modules.

### 1. Offline Agent Record Collection

The system should first collect real usage records from coding agents with minimal disruption.

Potential sources:

- Claude Code local records, telemetry, hooks, or wrappers.
- opencode local records, logs, hooks, or provider output.
- Manual upload from CLI or web UI.
- Local watcher that syncs session records.
- Git diff or PR information produced by an agent session.

Recommended collected fields:

- User.
- Project.
- Repository.
- Branch.
- Commit.
- Timestamp.
- Agent type.
- Session ID.
- User input.
- Assistant output or summary.
- Tool calls.
- Shell commands.
- File edit records.
- Error output.
- Token and cost information, if available.
- Local environment metadata.
- Final git diff or PR link, if available.

Collection should prioritize adoption and usefulness over completeness.

Recommended rollout order:

1. Manual upload or CLI upload.
2. Local watcher or local collector.
3. Optional unified agent wrapper.

### 2. Langfuse Session Foundation

Langfuse should own session and trace visualization where possible.

The in-house system should store business metadata and links instead of duplicating Langfuse's trace viewer.

Useful references stored in the in-house system:

- `langfuse_session_id`
- `langfuse_trace_id`
- Project.
- User.
- Owner.
- Case status.
- Problem type.
- Severity.
- AI analysis result.
- Human conclusion.
- Closure result.

### 3. AI Case Workflow

The in-house product's core entity is an AI case.

An AI case represents a problem, risk, failure, or review item found in AI agent usage.

Minimal case fields:

- Title.
- Source: manual, automatic detection, user feedback, offline log import.
- Related session, trace, or raw log.
- Project.
- Owner.
- Collaborators.
- Status.
- Severity.
- Problem type.
- AI analysis.
- Human conclusion.
- Handling action.
- Closure reason.
- Whether it was extracted into reusable experience.

Recommended first-stage status flow:

```text
To triage -> To analyze -> In progress -> To verify -> Closed
```

Recommended first-stage problem types:

- Incorrect model answer.
- Insufficient context.
- Tool-call failure.
- Command execution failure.
- Risky code modification.
- Requirement misunderstanding.
- Cost or latency anomaly.
- Permission or security issue.
- User workflow issue.
- Other.

### 4. AI-Assisted Session And Log Analysis

This is the main innovation point for stage one.

Input:

- Agent session.
- Tool calls.
- Shell logs.
- Git diff.
- Error output.
- User feedback.
- Langfuse trace.

Output:

- What happened.
- Likely failure point.
- Suggested ownership category.
- Suggested severity.
- Suggested owner or team.
- Recommended next steps.
- Whether the case is worth extracting into experience.
- Potential evaluation case, checklist, or usage guideline.

Suggested ownership categories:

- Model behavior issue.
- Tooling issue.
- User prompt or usage issue.
- Project configuration issue.
- Codebase issue.
- Workflow or process issue.
- Security or permission issue.
- Unknown.

Important boundary:

AI analysis should be advisory in stage one. It should not automatically assign final responsibility or close cases without human confirmation.

### 5. Frontend Console And Dashboard

The first-stage frontend should focus on operational clarity.

Core pages:

- Case list.
- Case detail.
- Session or trace link panel.
- AI analysis panel.
- Owner and status flow controls.
- Import records page.
- Dashboard.

Recommended dashboard metrics:

- AI session count.
- Connected users.
- Connected projects.
- Created case count.
- Case closure rate.
- Average closure time.
- Current open case count.
- Top problem types.
- Top projects or repositories.
- Top agent types.
- High-risk case count.
- AI analysis accepted or corrected rate.
- Extracted experience count.

## Proposed Architecture

```text
Claude Code / opencode local records
        |
        v
Offline collector / upload CLI / webhook
        |
        v
Ingestion API
        |
        +----> Langfuse
        |       - Session
        |       - Trace
        |       - Observation
        |
        +----> Object storage
        |       - Raw logs
        |       - Large payloads
        |
        +----> In-house issue-loop system
                - Case metadata
                - Workflow state
                - Ownership
                - AI analysis
                - Dashboards
                - Experience extraction
```

Storage boundary:

- Langfuse stores trace/session observability data.
- Object storage stores large raw logs and original payloads.
- The in-house system stores workflow metadata, indexes, AI analysis output, ownership, and dashboard aggregates.

## Suggested Data Model

### AgentSessionIndex

- `id`
- `external_session_id`
- `langfuse_session_id`
- `agent_type`
- `user_id`
- `project_id`
- `repository`
- `branch`
- `commit_sha`
- `started_at`
- `ended_at`
- `source`
- `raw_artifact_uri`
- `summary`

### AgentCase

- `id`
- `title`
- `source`
- `session_index_id`
- `langfuse_trace_id`
- `project_id`
- `owner_id`
- `status`
- `severity`
- `problem_type`
- `created_at`
- `updated_at`
- `closed_at`
- `closure_reason`
- `extracted_to_experience`

### AIAnalysis

- `id`
- `case_id`
- `model`
- `input_artifact_refs`
- `summary`
- `failure_point`
- `ownership_suggestion`
- `severity_suggestion`
- `next_steps`
- `experience_suggestion`
- `confidence`
- `human_feedback`
- `created_at`

### CaseEvent

- `id`
- `case_id`
- `event_type`
- `actor_id`
- `from_status`
- `to_status`
- `comment`
- `created_at`

### ExperienceItem

- `id`
- `source_case_id`
- `type`
- `title`
- `content`
- `project_id`
- `tags`
- `created_at`

Experience item types can include:

- Usage guideline.
- Failure mode.
- Checklist.
- Regression example.
- Prompt pattern.
- Tooling issue.

## Rollout Plan

### Stage 1: MVP, 2-4 Weeks

- Deploy Langfuse.
- Build offline collector MVP.
- Import Claude Code or opencode sessions.
- Build AI case workflow MVP.
- Build AI-assisted analysis MVP.
- Build basic dashboard and frontend console.
- Run with seed users and collect feedback.

### Stage 2

- Add automatic clustering for similar cases.
- Improve ownership rules.
- Add PR, commit, repository, and project integration.
- Build experience extraction workflow.
- Add human feedback on AI analysis accuracy.
- Improve collectors and coverage.

### Stage 3

- Introduce unified model gateway if adoption and governance needs are clear.
- Add budget and routing controls.
- Add evaluation dataset management.
- Add recipe registry.
- Add team-level AI usage standards.
- Add mature quality and risk dashboards.

## Risks And Mitigations

### Risk: Low Data Completeness

Offline records may be incomplete.

Mitigation:

- Treat records as evidence, not complete truth.
- Allow manual supplementing.
- Store raw artifacts.
- Link to Langfuse traces when available.

### Risk: Early Platform Adoption Friction

Large teams may resist a new workflow.

Mitigation:

- Start with seed users.
- Support manual upload first.
- Avoid forcing model gateway adoption.
- Show dashboards and concrete analysis examples early.

### Risk: AI Analysis Produces Incorrect Attribution

The automatic analysis may misjudge responsibility.

Mitigation:

- Mark analysis as suggestion.
- Require human confirmation for ownership and closure.
- Track whether users accept or correct analysis.

### Risk: Privacy Or Sensitive Data Exposure

Agent sessions may include code, secrets, credentials, or private user data.

Mitigation:

- Add redaction before upload where possible.
- Store raw artifacts with strict access control.
- Support project-level collection policies.
- Audit who viewed sensitive sessions.

### Risk: Product Scope Expands Too Quickly

The platform could become a broad LLMOps product too early.

Mitigation:

- Keep stage one focused on case workflow, AI analysis, and dashboard.
- Defer gateway, eval platform, recipe registry, and full knowledge base.

## Key Principle

Langfuse answers:

> What happened inside the AI session?

The in-house system should answer:

> What problem did this create, who owns it, what happened next, and what did the team learn?

