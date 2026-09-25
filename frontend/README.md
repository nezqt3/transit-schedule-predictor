# Frontend · диспетчерская

Диспетчерский дашборд: показывает последние NDTP-позиции на интерактивной карте, очередь внимания и историю выбранного терминала.

**Стек:** React 19 · TypeScript · Vite 8 · pnpm · react-router 7 · TanStack Query 5 · zustand 5 · axios · Leaflet · recharts · date-fns · lucide-react.
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

Фронт читает начальное состояние через `GET /api/v1/vehicles`, а последующие
NDTP-события получает по `WS /api/v1/ws`. REST-опрос с интервалом
`VITE_POLL_INTERVAL_MS` остаётся резервным при разрыве соединения.
Карта использует тайлы OpenStreetMap с видимой атрибуцией.
История выбранного терминала берётся из буфера backend через
`GET /api/v1/vehicles/{unit_id}/history`. `unit_id` — ID NDTP-терминала, не номер маршрута.
Маркеры показывают движение, остановку, устаревшие координаты и тревожные флаги;
очередь внимания состоит из тревог, устаревших данных и отсутствующих координат.
Порог актуальности координат — 30 секунд, движение означает скорость выше 2 км/ч.

Для прогноза нужны актуальное расписание и текущее отклонение `cur_dev_s`.
Два синтетических терминала из `emulator/config.json` не имеют такой привязки,
поэтому панель честно показывает «Пока недоступен», не подставляя вымышленные значения.
Успешные вызовы Backend ML API сохраняются в памяти и появляются в карточке
терминала через `GET /api/v1/predictions`.

## Исторический прогон

Страница `/replay` воспроизводит январский `test/traffic.csv` отдельно от NDTP.
Плановые остановки берутся из `test/schedule.csv`, а 353 точки с известным
фактом — из `labels_test.csv`. Для каждой точки frontend вызывает
`POST /api/v1/replay/predict/{sample_id}`; backend передаёт в ML только
телеметрию с `event_time` и `receive_time` не позже `T`. Факт отображается
после виртуального времени прибытия. На странице видны ошибки по целевым
остановкам и MAE модели рядом с baseline `cur_dev_s`.

Это локальная проверка на test из тех же суток, что train. Она показывает
работоспособность и ошибки записанного маршрута, но не заменяет проверку
на новом дне движения.
