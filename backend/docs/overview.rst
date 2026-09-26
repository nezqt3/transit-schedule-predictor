Архитектура
============

Поток данных Backend:

.. code-block:: text

   NDTP TCP -> parser -> TelemetryService -> Prediction Service -> ML Service
                              |
                              +-> REST API -> Dashboard

``app.ndtp`` изолирует бинарный протокол. ``TelemetryService`` хранит
ограниченную in-memory историю для демо. Prediction Service не загружает
модель, а обращается к отдельному ML Service.

Публичные маршруты
-------------------

* ``GET /api/v1/health``
* ``POST /api/v1/auth/token``
* ``POST /api/v1/auth/logout``
* ``/docs``, ``/redoc``, ``/openapi.json``

Маршруты vehicles, predictions и ``GET /api/v1/auth/me`` требуют сессию.
