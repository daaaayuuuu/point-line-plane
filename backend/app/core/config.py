from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
KNOWN_DEFAULT_SESSION_SECRETS = {
    "local-development-session-secret-change-me",
    "replace-with-a-long-random-secret",
}
KNOWN_DEFAULT_INVITE_CODES = {
    "local-development-invite",
    "replace-with-local-invite-code",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'data' / 'product_factory.db'}"
    auto_create_db: bool = False
    sqlite_lock_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)
    database_pool_timeout_seconds: float = Field(default=30, gt=0, le=120)
    frontend_origins: str = (
        "http://127.0.0.1:3000,http://localhost:3000,"
        "http://127.0.0.1:3001,http://localhost:3001,"
        "http://127.0.0.1:3102,http://localhost:3102"
    )

    session_cookie_name: str = "product_factory_session"
    session_ttl_hours: int = Field(default=72, ge=1, le=24 * 30)
    session_secret: SecretStr = SecretStr("local-development-session-secret-change-me")
    invite_codes: SecretStr = SecretStr("local-development-invite")

    codex_command: str = "codex"
    codex_auth_root: Path = BACKEND_ROOT / "data" / "codex-auth"
    codex_request_timeout_seconds: float = Field(default=15, gt=1, le=120)
    codex_login_timeout_seconds: float = Field(default=600, ge=60, le=1_800)
    codex_turn_timeout_seconds: float = Field(default=180, ge=30, le=600)

    ai_provider: str = "mock"
    ai_model: str = "mock-text-agent-v1"
    ai_base_url: str = "https://api.example.invalid/v1"
    ai_api_key: SecretStr = SecretStr("")
    ai_timeout_seconds: float = Field(default=30, gt=0, le=120)
    ai_max_attempts: int = Field(default=2, ge=1, le=3)
    ai_provider_verified: bool = False

    workspace_root: Path = BACKEND_ROOT / "data" / "workspaces"
    preview_ttl_hours: int = Field(default=72, ge=1, le=24 * 30)
    max_upload_bytes: int = Field(default=10_485_760, ge=1024, le=10_485_760)
    task_max_attempts: int = Field(default=2, ge=1, le=3)
    task_force_failure: bool = False
    coding_max_files: int = Field(default=24, ge=6, le=40)
    coding_max_file_bytes: int = Field(default=100_000, ge=1_024, le=500_000)
    coding_max_total_bytes: int = Field(default=500_000, ge=10_000, le=2_000_000)
    generated_execution_mode: str = "trusted_mock"
    external_execution_base_url: str = ""
    quality_command_timeout_seconds: float = Field(default=30, gt=1, le=300)
    quality_max_repairs: int = Field(default=2, ge=0, le=3)
    quality_force_failures: int = Field(default=0, ge=0, le=3)
    preview_startup_timeout_seconds: float = Field(default=10, gt=1, le=60)
    credential_store_root: Path = BACKEND_ROOT / "data" / "secrets"
    credential_master_key: SecretStr = SecretStr("")
    free_quota_units: int = Field(default=5_000, ge=0, le=100_000_000)
    ai_input_cost_microusd_per_million: int = Field(default=0, ge=0)
    ai_output_cost_microusd_per_million: int = Field(default=0, ge=0)
    cost_confirmation_threshold_microusd: int = Field(default=100_000, ge=0)
    deployment_enabled: bool = False
    deployment_mode: str = "mock"
    deployment_adapter_base_url: str = ""
    deployment_adapter_token: SecretStr = SecretStr("")
    deployment_timeout_seconds: float = Field(default=60, gt=1, le=600)
    deployment_default_region: str = "cn-beijing"
    delivery_root: Path = BACKEND_ROOT / "data" / "deliveries"
    delivery_max_bytes: int = Field(default=20_000_000, ge=100_000, le=100_000_000)
    github_sync_mode: str = "mock"
    github_adapter_base_url: str = ""
    github_adapter_token: SecretStr = SecretStr("")
    operations_token: SecretStr = SecretStr("local-development-operations-token")
    auth_rate_limit_attempts: int = Field(default=20, ge=2, le=1_000)
    auth_rate_limit_window_seconds: int = Field(default=300, ge=10, le=86_400)
    backup_root: Path = BACKEND_ROOT / "data" / "backups"
    backup_mode: str = "sqlite_local"
    backup_adapter_base_url: str = ""
    backup_adapter_token: SecretStr = SecretStr("")
    production_postgresql_required: bool = True

    @property
    def invite_code_values(self) -> tuple[str, ...]:
        return tuple(
            code.strip() for code in self.invite_codes.get_secret_value().split(",") if code.strip()
        )

    @property
    def origin_values(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @property
    def credential_key_bytes(self) -> bytes | None:
        encoded = self.credential_master_key.get_secret_value().strip()
        if not encoded:
            return None
        try:
            value = base64.urlsafe_b64decode(encoded.encode("ascii"))
        except (ValueError, UnicodeEncodeError, binascii.Error) as exc:
            raise ValueError("CREDENTIAL_MASTER_KEY must be URL-safe base64") from exc
        if len(value) != 32:
            raise ValueError("CREDENTIAL_MASTER_KEY must decode to exactly 32 bytes")
        return value

    @model_validator(mode="after")
    def validate_runtime_secrets(self) -> Settings:
        invite_codes = self.invite_code_values
        if not invite_codes:
            raise ValueError("INVITE_CODES must contain at least one code")
        if len(set(invite_codes)) != len(invite_codes):
            raise ValueError("INVITE_CODES must not contain duplicate codes")
        if self.generated_execution_mode not in {"trusted_mock", "external"}:
            raise ValueError("GENERATED_EXECUTION_MODE must be trusted_mock or external")
        if self.generated_execution_mode == "external" and not self.external_execution_base_url:
            raise ValueError("EXTERNAL_EXECUTION_BASE_URL is required for external execution")
        credential_key = self.credential_key_bytes
        if self.deployment_mode not in {"mock", "external"}:
            raise ValueError("DEPLOYMENT_MODE must be mock or external")
        if self.deployment_enabled and self.deployment_mode == "external":
            if not self.deployment_adapter_base_url.startswith("https://"):
                raise ValueError("DEPLOYMENT_ADAPTER_BASE_URL must use HTTPS")
            if not self.deployment_adapter_token.get_secret_value():
                raise ValueError("DEPLOYMENT_ADAPTER_TOKEN is required for external deployment")
        if self.github_sync_mode not in {"mock", "external"}:
            raise ValueError("GITHUB_SYNC_MODE must be mock or external")
        if self.github_sync_mode == "external":
            if not self.github_adapter_base_url.startswith("https://"):
                raise ValueError("GITHUB_ADAPTER_BASE_URL must use HTTPS")
            if not self.github_adapter_token.get_secret_value():
                raise ValueError("GITHUB_ADAPTER_TOKEN is required for external GitHub sync")
        if self.backup_mode not in {"sqlite_local", "external"}:
            raise ValueError("BACKUP_MODE must be sqlite_local or external")
        if self.backup_mode == "external":
            if not self.backup_adapter_base_url.startswith("https://"):
                raise ValueError("BACKUP_ADAPTER_BASE_URL must use HTTPS")
            if not self.backup_adapter_token.get_secret_value():
                raise ValueError("BACKUP_ADAPTER_TOKEN is required for external backup")
        if self.app_env.lower() in {"production", "prod"}:
            secret = self.session_secret.get_secret_value()
            if (
                len(secret) < 32
                or "replace-with" in secret
                or secret in KNOWN_DEFAULT_SESSION_SECRETS
            ):
                raise ValueError("SESSION_SECRET must be a strong value in production")
            if any(
                "replace-with" in code or code in KNOWN_DEFAULT_INVITE_CODES
                for code in invite_codes
            ):
                raise ValueError("INVITE_CODES must be replaced in production")
            if self.ai_provider != "mock" and not self.ai_api_key.get_secret_value():
                raise ValueError("AI_API_KEY is required for a real provider")
            if self.auto_create_db:
                raise ValueError("AUTO_CREATE_DB must be false in production; use Alembic")
            if credential_key is None:
                raise ValueError("CREDENTIAL_MASTER_KEY is required in production")
            if len(self.operations_token.get_secret_value()) < 32:
                raise ValueError("OPERATIONS_TOKEN must be a strong value in production")
            if self.production_postgresql_required and not self.database_url.startswith(
                ("postgresql://", "postgresql+psycopg://")
            ):
                raise ValueError("DATABASE_URL must use PostgreSQL in production")
            if self.backup_mode != "external":
                raise ValueError("BACKUP_MODE must be external in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
