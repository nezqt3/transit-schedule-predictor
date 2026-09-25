from fastapi import APIRouter

router = APIRouter()


@router.get(
    "",
    summary="Health check",
    description="Проверяет доступность Backend-сервиса.",
)
async def health_check() -> dict[str, str]:
    """
    Проверка состояния Backend.

    Returns:
        dict[str, str]: Текущее состояние сервиса.
    """

    return {
        "status": "ok",
        "service": "backend",
    }