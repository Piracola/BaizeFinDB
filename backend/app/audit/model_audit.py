from hashlib import sha256

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.audit_models import ModelCallLog

MODEL_AUDIT_PROMPT_HASH_VERSION = "sha256:v1"
MAX_ERROR_MESSAGE_LENGTH = 500
MAX_RESPONSE_EXCERPT_LENGTH = 1000


async def record_model_degradation(
    session: AsyncSession,
    *,
    call_site: str,
    primary_model: str,
    prompt: str,
    fallback_model: str | None = None,
    error: Exception | None = None,
    response_excerpt: str | None = None,
    details: dict[str, object] | None = None,
    store_raw_prompt: bool | None = None,
    settings: Settings | None = None,
    commit: bool = True,
) -> ModelCallLog:
    should_store_raw_prompt = _should_store_raw_prompt(store_raw_prompt, settings)
    error_message = _short_error_message(error)
    audit_details = {
        **(details or {}),
        "prompt_hash_version": MODEL_AUDIT_PROMPT_HASH_VERSION,
        "raw_prompt_saved": should_store_raw_prompt,
    }

    log = ModelCallLog(
        call_site=call_site,
        primary_model=primary_model,
        fallback_model=fallback_model,
        status="fallback" if fallback_model else "degraded",
        error_type=error.__class__.__name__ if error is not None else None,
        error_message=error_message,
        prompt_hash=_prompt_hash(prompt),
        prompt_length=len(prompt),
        raw_prompt=prompt if should_store_raw_prompt else None,
        response_excerpt=_response_excerpt(response_excerpt),
        details=audit_details,
    )
    session.add(log)
    await session.flush()

    if commit:
        await session.commit()
        await session.refresh(log)

    return log


def _should_store_raw_prompt(
    store_raw_prompt: bool | None,
    settings: Settings | None,
) -> bool:
    if store_raw_prompt is not None:
        return store_raw_prompt

    return (settings or get_settings()).model_audit_store_raw_prompt


def _prompt_hash(prompt: str) -> str:
    return sha256(prompt.encode("utf-8")).hexdigest()


def _short_error_message(error: Exception | None) -> str | None:
    if error is None:
        return None

    message = str(error).strip()
    if len(message) <= MAX_ERROR_MESSAGE_LENGTH:
        return message

    return f"{message[: MAX_ERROR_MESSAGE_LENGTH - 3]}..."


def _response_excerpt(response_excerpt: str | None) -> str | None:
    if response_excerpt is None:
        return None

    if len(response_excerpt) <= MAX_RESPONSE_EXCERPT_LENGTH:
        return response_excerpt

    return f"{response_excerpt[: MAX_RESPONSE_EXCERPT_LENGTH - 3]}..."
