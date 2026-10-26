def escape_like(value: str) -> str:
    """Escapa curingas de LIKE/ILIKE (use com ``escape="\\\\"``)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
