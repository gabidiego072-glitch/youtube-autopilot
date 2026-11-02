"""YouTube metadata limits, checked before anything is stored or uploaded."""

TITLE_MAX_CHARS = 100
DESCRIPTION_MAX_CHARS = 5000
TAGS_MAX_TOTAL_CHARS = 500
FORBIDDEN_CHARS = ("<", ">")


def normalize_tags(tags: list[str]) -> list[str]:
    """Trim, drop empties and '#', and de-duplicate case-insensitively (order kept)."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in tags:
        tag = raw.strip().lstrip("#").strip()
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            result.append(tag)
    return result


def tags_length(tags: list[str]) -> int:
    """YouTube counts commas between tags and quotes around tags containing spaces."""
    if not tags:
        return 0
    total = sum(len(tag) + (2 if " " in tag else 0) for tag in tags)
    return total + len(tags) - 1


def fit_tags(tags: list[str], limit: int = TAGS_MAX_TOTAL_CHARS) -> list[str]:
    """Keep tags in priority order until the next one would exceed the limit."""
    kept: list[str] = []
    for tag in tags:
        if tags_length([*kept, tag]) > limit:
            break
        kept.append(tag)
    return kept


def validate_metadata(title: str, description: str, tags: list[str]) -> list[str]:
    problems: list[str] = []
    if not title.strip():
        problems.append("Title is empty.")
    if len(title) > TITLE_MAX_CHARS:
        problems.append(f"Title exceeds {TITLE_MAX_CHARS} characters ({len(title)}).")
    if len(description) > DESCRIPTION_MAX_CHARS:
        problems.append(f"Description exceeds {DESCRIPTION_MAX_CHARS} characters ({len(description)}).")
    for field_name, value in (("Title", title), ("Description", description)):
        if any(ch in value for ch in FORBIDDEN_CHARS):
            problems.append(f"{field_name} contains '<' or '>', which YouTube rejects.")
    if tags_length(tags) > TAGS_MAX_TOTAL_CHARS:
        problems.append(f"Tags exceed {TAGS_MAX_TOTAL_CHARS} characters in total.")
    return problems
