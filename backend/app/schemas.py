from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import AIAnalysisStatus, CaseSeverity, CaseSource, CaseStatus, ProblemType, UserRole


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(ORMModel):
    id: str
    email: str
    display_name: str
    role: UserRole
    is_active: bool


class UserCreate(BaseModel):
    email: str
    display_name: str
    password: str = Field(min_length=8)
    role: UserRole = UserRole.member


class ProjectCreate(BaseModel):
    name: str
    repository: str | None = None
    default_owner_id: str | None = None


class ProjectRead(ORMModel):
    id: str
    name: str
    repository: str | None
    default_owner_id: str | None
    is_active: bool


class SessionImport(BaseModel):
    external_session_id: str | None = None
    langfuse_session_id: str | None = None
    langfuse_trace_id: str | None = None
    langfuse_url: str | None = None
    agent_type: str = "unknown"
    user_email: str | None = None
    project_name: str | None = None
    repository: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    source: str = "api"
    summary: str | None = None
    user_input: str | None = None
    assistant_output: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    shell_commands: list[dict[str, Any]] = Field(default_factory=list)
    file_edits: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    git_diff: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] | None = None


class SessionRead(ORMModel):
    id: str
    external_session_id: str | None
    langfuse_session_id: str | None
    langfuse_trace_id: str | None
    langfuse_url: str | None
    agent_type: str
    user_id: str | None
    project_id: str | None
    repository: str | None
    branch: str | None
    commit_sha: str | None
    source: str
    raw_artifact_uri: str | None
    summary: str | None
    metadata_json: dict[str, Any]
    created_at: datetime


class CaseCreate(BaseModel):
    title: str
    source: CaseSource = CaseSource.manual
    session_id: str | None = None
    project_id: str | None = None
    owner_id: str | None = None
    severity: CaseSeverity = CaseSeverity.medium
    problem_type: str = ProblemType.other.value
    scene_description: str | None = None
    expected_result: str | None = None
    actual_result: str | None = None
    reproducible: bool | None = None
    feedback_reporter: str | None = None
    responsible_owner: str | None = None
    tags: list[str] = Field(default_factory=list)
    closure_practice: str | None = None
    feedback_acceptance_conclusion: str | None = None

    @field_validator("problem_type")
    @classmethod
    def normalize_problem_type(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("problem_type cannot be empty")
        if len(normalized) > 128:
            raise ValueError("problem_type cannot exceed 128 characters")
        return normalized


class CaseUpdate(BaseModel):
    title: str | None = None
    owner_id: str | None = None
    status: CaseStatus | None = None
    severity: CaseSeverity | None = None
    problem_type: str | None = None
    scene_description: str | None = None
    expected_result: str | None = None
    actual_result: str | None = None
    reproducible: bool | None = None
    feedback_reporter: str | None = None
    responsible_owner: str | None = None
    tags: list[str] | None = None
    closure_practice: str | None = None
    feedback_acceptance_conclusion: str | None = None
    human_conclusion: str | None = None
    handling_action: str | None = None
    closure_reason: str | None = None

    @field_validator("problem_type")
    @classmethod
    def normalize_problem_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("problem_type cannot be empty")
        if len(normalized) > 128:
            raise ValueError("problem_type cannot exceed 128 characters")
        return normalized


class CaseRead(ORMModel):
    id: str
    title: str
    source: CaseSource
    session_id: str | None
    project_id: str | None
    owner_id: str | None
    status: CaseStatus
    severity: CaseSeverity
    problem_type: str
    ai_analysis_status: AIAnalysisStatus
    scene_description: str | None
    expected_result: str | None
    actual_result: str | None
    reproducible: bool | None
    feedback_reporter: str | None
    responsible_owner: str | None
    tags: list[Any]
    closure_practice: str | None
    feedback_acceptance_conclusion: str | None
    human_conclusion: str | None
    handling_action: str | None
    closure_reason: str | None
    extracted_to_experience: bool
    created_by_id: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class AIAnalysisRead(ORMModel):
    id: str
    case_id: str
    model: str | None
    summary: str | None
    failure_point: str | None
    ownership_suggestion: str | None
    severity_suggestion: str | None
    next_steps: list[Any]
    experience_suggestion: str | None
    confidence: float | None
    human_feedback: str | None
    error_message: str | None
    created_at: datetime


class AIAnalysisFeedback(BaseModel):
    human_feedback: str


class CaseEventCreate(BaseModel):
    event_type: str = "comment"
    comment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseEventRead(ORMModel):
    id: str
    case_id: str
    event_type: str
    actor_id: str | None
    from_status: str | None
    to_status: str | None
    comment: str | None
    metadata_json: dict[str, Any]
    created_at: datetime


class CaseDetail(CaseRead):
    analyses: list[AIAnalysisRead] = Field(default_factory=list)
    events: list[CaseEventRead] = Field(default_factory=list)
    session: SessionRead | None = None



class ResponsibleOwnerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    responsibility_area: str | None = None


class ResponsibleOwnerRead(ORMModel):
    id: str
    name: str
    responsibility_area: str | None
    created_at: datetime


class ExperienceCreate(BaseModel):
    type: str = "failure_mode"
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)


class ExperienceRead(ORMModel):
    id: str
    source_case_id: str | None
    type: str
    title: str
    content: str
    project_id: str | None
    tags: list[Any]
    created_at: datetime
