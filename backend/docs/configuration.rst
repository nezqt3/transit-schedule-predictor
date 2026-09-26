Конфигурация
=============

Все параметры берутся из environment или ``.env``.

.. list-table:: Основные переменные
   :header-rows: 1

   * - Переменная
     - Назначение
   * - ``ML_SERVICE_URL``
     - URL ML inference service
   * - ``ML_MAX_IN_FLIGHT``
     - Максимум одновременных запросов в ML; остальные ждут в backend
   * - ``ML_WORKERS``
     - Число CPU-процессов ML в Compose
   * - ``NDTP_HOST``, ``NDTP_PORT``
     - TCP listener телеметрии
   * - ``RUNTIME_SCHEDULE_PATH``
     - Плановое расписание, только поля ``tr_id``, ``tt_action_item_id``, ``time_begin``, ``geom``
   * - ``RUNTIME_TRAFFIC_PATH``
     - Явное соответствие ``tr_id`` и NDTP ``unit_id``
   * - ``RUNTIME_POINTS_PATH``
     - Опубликованные входные точки ``cur_dev_s`` для исторического NDTP
   * - ``SOURCE_TIMEZONE``
     - Зона CSV без UTC-offset; по умолчанию ``Europe/Moscow``
   * - ``PREDICTION_INTERVAL_S``
     - Минимальный логический интервал запросов ML на терминал
   * - ``RISK_MEDIUM_PROBABILITY``, ``RISK_HIGH_PROBABILITY``
     - Пороги риска при калиброванной ``p_late``; без неё используются пороги задержки
   * - ``DEMO_UNITS``, ``DEMO_INITIAL_DELAY_S``
     - Явно синтетический план для терминалов эмулятора организаторов
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

Стандартный Compose монтирует план и файл соответствия терминалов; он не
монтирует ``points.csv`` и test-метки. Дополнительный
``docker-compose.replay.yml`` включает их только для ретроспективной диагностики.
``docker-compose.benchmark.yml`` подставляет отдельный синтетический план для
нагрузочного прогона.
