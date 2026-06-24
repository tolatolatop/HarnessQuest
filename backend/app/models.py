import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    member = "member"
    viewer = "viewer"


class CaseStatus(str, enum.Enum):
    to_triage = "to_triage"
    to_analyze = "to_analyze"
    in_progress = "in_progress"
    to_verify = "to_verify"
    closed = "closed"


class CaseSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ProblemType(str, enum.Enum):
    incorrect_model_answer = "incorrect_model_answer"
    insufficient_context = "insufficient_context"
    tool_call_failure = "tool_call_failure"
    command_execution_failure = "command_execution_failure"
    risky_code_change = "risky_code_change"
    requirement_misunderstanding = "requirement_misunderstanding"
    cost_or_latency_anomaly = "cost_or_latency_anomaly"
    permission_or_security_issue = "permission_or_security_issue"
    user_workflow_issue = "user_workflow_issue"
    other = "other"


class CaseSource(str, enum.Enum):
    manual = "manual"
    automatic_detection = "automatic_detection"
    user_feedback = "user_feedback"
    offline_log_import = "offline_log_import"


class AIAnalysisStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.member)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    repository: Mapped[str | None] = mapped_column(String(512), nullable=True)
    default_owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    default_owner: Mapped[User | None] = relationship("User")


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    external_session_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    langfuse_session_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    langfuse_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    agent_type: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    repository: Mapped[str | None] = mapped_column(String(512), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(128), default="api")
    raw_artifact_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User | None] = relationship("User")
    project: Mapped[Project | None] = relationship("Project")


class AgentCase(Base):
    __tablename__ = "agent_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    title: Mapped[str] = mapped_column(String(512))
    source: Mapped[CaseSource] = mapped_column(Enum(CaseSource), default=CaseSource.manual)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("agent_sessions.id"), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus), default=CaseStatus.to_triage, index=True)
    severity: Mapped[CaseSeverity] = mapped_column(Enum(CaseSeverity), default=CaseSeverity.medium, index=True)
    problem_type: Mapped[str] = mapped_column(String(128), default=ProblemType.other.value, index=True)
    ai_analysis_status: Mapped[AIAnalysisStatus] = mapped_column(
        Enum(AIAnalysisStatus), default=AIAnalysisStatus.pending
    )
    scene_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    reproducible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    feedback_reporter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsible_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    closure_practice: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_acceptance_conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    handling_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    closure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_to_experience: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[AgentSession | None] = relationship("AgentSession")
    project: Mapped[Project | None] = relationship("Project")
    owner: Mapped[User | None] = relationship("User", foreign_keys=[owner_id])
    created_by: Mapped[User | None] = relationship("User", foreign_keys=[created_by_id])
    analyses: Mapped[list["AIAnalysis"]] = relationship(
        "AIAnalysis", back_populates="case", cascade="all, delete-orphan"
    )
    events: Mapped[list["CaseEvent"]] = relationship("CaseEvent", back_populates="case", cascade="all, delete-orphan")


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    case_id: Mapped[str] = mapped_column(ForeignKey("agent_cases.id"), index=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_artifact_refs: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_point: Mapped[str | None] = mapped_column(Text, nullable=True)
    ownership_suggestion: Mapped[str | None] = mapped_column(String(128), nullable=True)
    severity_suggestion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    next_steps: Mapped[list] = mapped_column(JSON, default=list)
    experience_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    human_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped[AgentCase] = relationship("AgentCase", back_populates="analyses")


class CaseEvent(Base):
    __tablename__ = "case_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    case_id: Mapped[str] = mapped_column(ForeignKey("agent_cases.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(128))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped[AgentCase] = relationship("AgentCase", back_populates="events")
    actor: Mapped[User | None] = relationship("User")



class ResponsibleOwner(Base):
    __tablename__ = "responsible_owners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExperienceItem(Base):
    __tablename__ = "experience_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    source_case_id: Mapped[str | None] = mapped_column(ForeignKey("agent_cases.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
