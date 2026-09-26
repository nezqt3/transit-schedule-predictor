Авторизация
============

Для входа отправьте OAuth2 form на ``POST /api/v1/auth/token``:

.. code-block:: bash

   curl -c cookies.txt -X POST http://localhost:8000/api/v1/auth/token \
     -H 'Content-Type: application/x-www-form-urlencoded' \
     -d 'username=dispatcher&password=transport'

Backend проверит Argon2-хеш пароля из PostgreSQL и установит JWT в
``HttpOnly`` cookie. Браузер не может прочитать
её из JavaScript; cookie отправляется автоматически для ``/api/v1``.
Для CLI и Swagger тот же JWT можно передать как ``Authorization: Bearer <token>``.

При первом старте создаётся ``auth_users`` и bootstrap-учётная запись из
``AUTH_BOOTSTRAP_USERNAME`` / ``AUTH_BOOTSTRAP_PASSWORD``. Существующая запись не
перезаписывается при последующих запусках.

В production обязательно задайте свои ``AUTH_BOOTSTRAP_PASSWORD`` и ``AUTH_JWT_SECRET``,
включите HTTPS и ``AUTH_COOKIE_SECURE=true``. Выход выполняется через
``POST /api/v1/auth/logout``.
