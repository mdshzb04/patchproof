def slug(name: str) -> str:
    cleaned = name.strip().lower()
    return "-".join(part for part in cleaned.split() if part)
