from enum import StrEnum


class ProjectStage(StrEnum):
    REQUIREMENTS = "REQUIREMENTS"
    PRD_REVIEW = "PRD_REVIEW"
    SOLUTION_REVIEW = "SOLUTION_REVIEW"
    DEVELOPMENT = "DEVELOPMENT"
    PREVIEW_REVIEW = "PREVIEW_REVIEW"
    DEPLOYMENT = "DEPLOYMENT"
    DELIVERY = "DELIVERY"
    PAUSED = "PAUSED"


class ProjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DELETED = "DELETED"


class ArtifactType(StrEnum):
    PRD = "prd"
    SOLUTION = "solution"
    FAILURE_REPORT = "failure_report"
    CHANGE_REQUEST = "change_request"


class ArtifactStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EventType(StrEnum):
    PROGRESS = "progress"
    RETRY = "retry"
    DONE = "done"
    ERROR = "error"


class ProductGraphStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class JourneyNodeType(StrEnum):
    PERSONA = "persona"
    INPUT = "input"
    AI_ACTION = "ai_action"
    OUTPUT = "output"
    PERSISTENCE = "persistence"


class JourneyNodeStatus(StrEnum):
    READY = "ready"
    NEEDS_DECISION = "needs_decision"
    ISSUE = "issue"
    OPTIMIZED = "optimized"


class DecisionStatus(StrEnum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"


class SimulationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class SimulationStepStatus(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"
    FAILED = "failed"


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class FindingStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ChangeRequestSource(StrEnum):
    DECISION = "decision"
    SIMULATION = "simulation"
    PREVIEW_FEEDBACK = "preview_feedback"


class ChangeRequestStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    QUEUED = "queued"
    APPLIED = "applied"
    CANCELED = "canceled"


class ScopeClassification(StrEnum):
    IN_SCOPE = "in_scope"
    NEW_SCOPE = "new_scope"
    BUG = "bug"


class DevelopmentWorkspaceStatus(StrEnum):
    READY = "ready"
    BUSY = "busy"
    PAUSED = "paused"


class DevelopmentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ToolExecutionStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class QualityRunStatus(StrEnum):
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class QualityCheckKind(StrEnum):
    COMPILE = "compile"
    PYTEST = "pytest"
    RUNTIME_SMOKE = "runtime_smoke"


class RepairAttemptStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PreviewRuntimeStatus(StrEnum):
    PROVISIONING = "provisioning"
    READY = "ready"
    FAILED = "failed"
    STOPPED = "stopped"
    EXPIRED = "expired"


class CredentialStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    INVALID = "invalid"
    REVOKED = "revoked"
    EXPIRED = "expired"


class CredentialScope(StrEnum):
    DEVELOPMENT = "development"
    RUNTIME = "runtime"
    BOTH = "both"


class UsageSource(StrEnum):
    MOCK = "mock"
    PLATFORM_FREE = "platform_free"
    USER_KEY = "user_key"


class CostAuthorizationStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CONSUMED = "consumed"
    EXPIRED = "expired"
    CANCELED = "canceled"


class DeploymentStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    SIMULATED = "simulated"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
