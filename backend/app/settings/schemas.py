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


class EditableSettingsField(BaseModel):
    key: str
    label: str
    group: str
    input_type: str
    value: str | bool | int | None = None
    configured: bool
    secret: bool
    choices: list[str] = Field(default_factory=list)
    help_text: str


class EditableSettingsAuth(BaseModel):
    admin_token_configured: bool
    local_write_without_token: bool
    header_name: str = "X-BaizeFinDB-Settings-Token"


class EditableSettingsRead(BaseModel):
    generated_at: datetime
    report_type: str = "editable_settings"
    mode: str = "editable_local_env"
    env_file: str = ".env"
    write_boundary: str
    auth: EditableSettingsAuth
    fields: list[EditableSettingsField]
    status: SettingsStatusRead


class EditableSettingsUpdate(BaseModel):
    values: dict[str, str | bool | int | None] = Field(default_factory=dict)
    clear: list[str] = Field(default_factory=list)


class EditableSettingsSaveResult(BaseModel):
    saved: bool
    updated_keys: list[str]
    unchanged_secret_keys: list[str] = Field(default_factory=list)
    env_file: str = ".env"
    restart_note: str
    settings: EditableSettingsRead


class SettingsConnectionTestRequest(BaseModel):
    target: str = Field(pattern="^(server|tushare|telegram|model|all)$")


class SettingsConnectionCheck(BaseModel):
    name: str
    status: str
    detail: str


class SettingsConnectionTestResult(BaseModel):
    generated_at: datetime
    report_type: str = "settings_connection_test"
    target: str
    status: str
    boundary: str
    checks: list[SettingsConnectionCheck]
