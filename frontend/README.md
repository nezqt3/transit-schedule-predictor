# Frontend · диспетчерская

Диспетчерский дашборд: показывает телеметрию NDTP из Backend API и историю по выбранному терминалу.

**Стек:** React 19 · TypeScript · Vite 8 · pnpm · react-router 7 · TanStack Query 5 · zustand 5 · axios · recharts · date-fns · lucide-react.
Линтеры и UI-фреймворки сознательно не подключены — стили это один CSS с токенами (`src/styles/tokens.css`).

## Структура

```text
src/
├── main.tsx              # точка входа
├── app/                  # композиция приложения
│   ├── App.tsx
│   ├── Providers.tsx     # QueryClient + Router
│   └── router.tsx        # таблица маршрутов
├── config/               # env-конфиг (единственное место чтения import.meta.env)
├── pages/                # страницы = маршруты, только композиция
├── components/layout/    # AppShell, NavBar
├── features/             # по смыслу: health, vehicles
│   └── <feature>/api.ts  # запрос + react-query хук фичи
├── lib/                  # примитивы без UI: http, queryClient, формат, чтение телеметрии
├── store/                # zustand: выбранное ТС + локальная история скорости
├── styles/               # tokens.css + globals.css
└── types/api.ts          # зеркало pydantic-схем backend
```

Правила: компонент страницы не ходит в сеть сам — только через `features/*/api.ts`; поля ответа backend'а описаны в `types/api.ts`, новый тип добавляется туда, а не в компонент.

Дашборд защищён формой входа. JWT хранится только в `HttpOnly` cookie и не
доступен JavaScript. При перезагрузке `AuthBootstrap` проверяет cookie через
`GET /api/v1/auth/me`; при `401` пользователь возвращается на `/login`.

## Локальный запуск

```bash
cp .env.example .env
pnpm install --frozen-lockfile
pnpm dev            # http://localhost:5173
```

`pnpm dev` проксирует `/api`, `/docs`, `/redoc`, `/openapi.json` на `BACKEND_PROXY_TARGET`
(по умолчанию `http://127.0.0.1:8000`), поэтому backend должен быть запущен:

```bash
cd backend && uvicorn app.main:app --port 8000
./scripts/start_emulator.sh   # NDTP-телеметрия в backend по TCP :9201
```

Другие команды: `pnpm build` (типизация + прод-сборка в `dist/`), `pnpm preview`, `pnpm typecheck`.

## В Docker

```bash
make up-frontend          # прод: nginx на :8080
make up-frontend-dev      # профиль dev: vite + HMR на :5173
```

Прод-контейнер — двухстадийная сборка: `node:22-alpine` + pnpm (кеш магазина через
BuildKit cache mount) собирает статику, дальше `nginxinc/nginx-unprivileged` отдаёт SPA и
проксирует `/api` на backend. Адрес backend'а берётся из `BACKEND_UPSTREAM`, порт из
`LISTEN_PORT` — подстановка env идёт через nginx-шаблон при старте.

## Данные и обновление

Сейчас фронт читает телеметрию polling'ом (`GET /api/v1/vehicles`, интервал
`VITE_POLL_INTERVAL_MS`). WebSocket в интерфейсе ещё не подключён: backend не отдаёт
`/api/v1/ws`, инциденты и `cur_dev_s` тоже не экспортирует, поэтому панель прогноза задержки
не сделана — её добавим вместе с этими эндпоинтами.
