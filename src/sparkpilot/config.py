from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPARKPILOT_", case_sensitive=False)

    app_name: str = "SparkPilot API"
    environment: str = "dev"
    database_url: str = "sqlite:///./sparkpilot.db"
    dry_run_mode: bool = True
    aws_region: str = "us-east-1"
    log_group_prefix: str = "/sparkpilot/runs"
    emr_release_label: str = "emr-7.10.0-latest"
    emr_execution_role_arn: str = "arn:aws:iam::111111111111:role/SparkPilotEmrExecutionRole"
    queue_batch_size: int = 20
    poll_interval_seconds: int = 15
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [item.strip() for item in self.cors_origins.split(",")]
        return [item for item in origins if item]


@lru_cache
def get_settings() -> Settings:
    return Settings()
