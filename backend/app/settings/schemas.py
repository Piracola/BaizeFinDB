from datetime import datetime

from pydantic import BaseModel, Field


class SettingsReadinessCheck(BaseModel):
    name: str
    status: str
    detail: str


class SettingsReadinessSummary(BaseModel):
    check_count: int
    ok_count: int
    warning_count: int
    failure_count: int


class TushareSettingsStatus(BaseModel):
    token_configured: bool
    anns_d_beat_enabled: bool
    anns_d_beat_interval_seconds: int


class TelegramSettingsStatus(BaseModel):
    bot_token_configured: bool
    allowed_chat_count: int
    webhook_secret_enabled: bool
    require_binding: bool
    push_enabled: bool


class ModelSettingsStatus(BaseModel):
    status: str
    analysis_enabled: bool
    provider: str
    primary_model_configured: bool
    fallback_model_configured: bool
    custom_base_url_configured: bool
    openai_api_key_configured: bool
    model_api_key_configured: bool
    raw_prompt_storage_enabled: bool
    summary: SettingsReadinessSummary
    checks: list[SettingsReadinessCheck] = Field(default_factory=list)


class SettingsStatusRead(BaseModel):
    generated_at: datetime
    report_type: str = "settings_status"
    mode: str = "read_only_env"
    read_only_boundary: str
    config_source: str = "environment"
    tushare: TushareSettingsStatus
    telegram: TelegramSettingsStatus
    model: ModelSettingsStatus
