Конфигурация
=============

Все параметры берутся из environment или ``.env``.

.. list-table:: Основные переменные
   :header-rows: 1

   * - Переменная
     - Назначение
   * - ``ML_SERVICE_URL``
     - URL ML inference service
   * - ``NDTP_HOST``, ``NDTP_PORT``
     - TCP listener телеметрии
   * - ``RUNTIME_SCHEDULE_PATH``
     - Файл расписания runtime lookup
   * - ``AUTH_BOOTSTRAP_USERNAME``, ``AUTH_BOOTSTRAP_PASSWORD``
     - Данные для однократного создания первого диспетчера в PostgreSQL
   * - ``AUTH_JWT_SECRET``
     - Секрет подписи JWT
   * - ``AUTH_TOKEN_EXPIRE_MINUTES``
     - Срок жизни сессии
   * - ``AUTH_COOKIE_SECURE``
     - Передавать cookie только по HTTPS
   * - ``POSTGRES_*``
     - Подключение к базе с таблицей ``auth_users``
