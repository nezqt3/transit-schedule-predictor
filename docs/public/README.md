# Публичные документы

Собранные документы закоммичены в Git — ничего запускать не нужно,
достаточно открыть файлы из репозитория.

| Файл | Что внутри |
| --- | --- |
| [`pydoc/index.html`](pydoc/index.html) | Полная PyDoc (Sphinx): обзор, аутентификация, конфигурация, API backend, исходники модулей |
| [`api.html`](api.html) | OpenAPI-спецификация в Swagger UI: все эндпоинты, схемы запросов/ответов, требования авторизации |
| [`openapi.json`](openapi.json) | Машиночитаемая схема: импорт в Postman или вставка в <https://redocly.github.io/redoc/> |

`api.html` берётся из `docs/api-viewer.html`, остальное генерируется.

Пересборка после изменений в коде или документации:

```bash
make docs
```

Живой Swagger — в запущенном backend: <http://localhost:8000/docs>
и <http://localhost:8000/redoc>.
