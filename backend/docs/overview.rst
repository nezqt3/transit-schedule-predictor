Архитектура
============

Поток данных Backend:

.. code-block:: text

   NDTP TCP -> parser -> TelemetryService -> RuntimePrediction -> ML Service
                              |                    |
                              |                    +-> IncidentStore
                              +-> REST / WebSocket -> Dashboard

``app.ndtp`` изолирует бинарный протокол. ``TelemetryService`` хранит
ограниченную in-memory историю. ``RuntimePrediction`` сопоставляет терминал с
рейсом, выбирает первую остановку в ``(T+10 мин, T+15 мин]`` и вызывает
отдельный ML Service. Для старого NDTP-потока используется время самого
пакета; ускорение replay меняет темп передачи, но не это логическое время.
Timestamp без зоны в исходных CSV интерпретируется в ``SOURCE_TIMEZONE``
(``Europe/Moscow`` по умолчанию), а внутри backend приводится к UTC.

Текущий ``cur_dev_s`` берётся из уже опубликованной входной точки только в
историческом режиме или вычисляется по подтверждённой GPS-остановке. Если
источник недоступен, прогноз не подменяется нулём. Отдельный режим эмулятора
использует явно синтетический план и помечает результат как ``demo``.

Прогнозы и инциденты хранятся в памяти backend. PostgreSQL хранит данные
авторизации; потеря БД отключает вход, backend продолжает принимать NDTP.

Публичные маршруты
-------------------

* ``GET /api/v1/health``
* ``POST /api/v1/auth/token``
* ``POST /api/v1/auth/logout``
* ``/docs``, ``/redoc``, ``/openapi.json``

Маршруты ``vehicles``, ``predictions``, ``incidents``, ``metrics``, ``replay``
и ``GET /api/v1/auth/me`` требуют сессию. ``WS /api/v1/ws`` отправляет
``vehicle_update``, ``prediction_update``, ``incident`` и ``heartbeat``.
