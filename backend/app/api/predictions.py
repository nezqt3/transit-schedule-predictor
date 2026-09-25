from fastapi import APIRouter

from app.schemas.prediction import (
    PredictionRequest,
    PredictionResponse,
)

router = APIRouter()


@router.post(
    "",
    response_model=PredictionResponse,
    summary="Получить прогноз задержки",
    description=(
        "Возвращает прогноз отклонения транспортного средства "
        "от расписания на горизонте 10–15 минут."
    ),
)
async def predict(
    request: PredictionRequest,
) -> PredictionResponse:
    """
    Выполняет прогноз задержки транспортного средства.

    В production здесь будет вызов ML Service.

    Args:
        request:
            Текущее состояние транспортного средства.

    Returns:
        PredictionResponse:
            Прогноз задержки в секундах.
    """

    # MOCK до подключения ML Service
    prediction = request.cur_dev_s

    return PredictionResponse(
        tr_id=request.tr_id,
        prediction=prediction,
        model_version="mock-0.1",
    )