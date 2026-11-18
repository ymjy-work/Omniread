MAX_CHAPTER_INDEX = 193


class InvalidRealmError(ValueError):
    pass


def chapter_range(level: str, progress: int | None) -> tuple[int, int | None]:
    """past 返回 (1, progress)；full 返回 (1, None)。"""
    if level == "past":
        if progress is None or not 1 <= progress <= MAX_CHAPTER_INDEX:
            raise InvalidRealmError(
                f"past 进度的 progress 必须在 1..{MAX_CHAPTER_INDEX}"
            )
        return 1, progress
    if level == "full":
        return 1, None
    raise InvalidRealmError("level 必须是 past 或 full")
