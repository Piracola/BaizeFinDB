import re

URL_PATTERN = re.compile(
    r"https?://[^\s，。；;、)）]+|www\.[^\s，。；;、)）]+",
    re.IGNORECASE,
)
DOMAIN_PATTERN = re.compile(
    r"\b(?:[a-z0-9-]+\.)+[a-z]{2,24}\b",
    re.IGNORECASE,
)


def redact_source_locators(text: str) -> str:
    without_urls = URL_PATTERN.sub("[source omitted]", text)
    return DOMAIN_PATTERN.sub("[source omitted]", without_urls)


def truncate_text(text: str, max_length: int) -> str:
    stripped = text.strip()
    if len(stripped) <= max_length:
        return stripped

    return f"{stripped[: max_length - 3].rstrip()}..."
