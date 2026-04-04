PLATFORMS = ["zepto", "blinkit"]


def normalize_platform(platform: str | None) -> str | None:
    if not platform:
        return None
    value = platform.strip().lower()
    return value if value in PLATFORMS else None
