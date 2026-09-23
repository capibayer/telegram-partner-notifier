import re

EMAIL_RE = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
    re.IGNORECASE,
)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    if not email:
        return False
    normalized = normalize_email(email)
    return bool(re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", normalized))


def extract_emails_from_text(text: str) -> list[str]:
    if not text:
        return []
    emails = []
    for match in EMAIL_RE.findall(text):
        normalized = normalize_email(match)
        if normalized and normalized not in emails:
            emails.append(normalized)
    return emails


def extract_email_from_chat_title(title: str):
    if not title:
        return None
    matches = extract_emails_from_text(title)
    return matches[0] if matches else None


def extract_email_from_chat(title: str, description: str = ""):
    return extract_email_from_chat_title(title) or extract_email_from_chat_title(description)


def normalize_email_list(raw_text):
    if not raw_text:
        return []

    emails: list[str] = []
    seen: set[str] = set()
    for line in raw_text.splitlines():
        candidate = normalize_email(line.strip())
        if not candidate:
            continue
        if candidate in seen:
            continue
        if is_valid_email(candidate):
            seen.add(candidate)
            emails.append(candidate)
    return emails
