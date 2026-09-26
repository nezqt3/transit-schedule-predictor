import { MapPin } from 'lucide-react'

import { useDashboardStore } from '@/store/dashboard'
import type { ReplayFleetVehicle, ReplayOutcome } from '@/types/replay'
import { currentPoint, currentRun, janClock, janMs, stopLabel } from './fleetClock'

const signed = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(0)} с`

type Props = { vehicle: ReplayFleetVehicle | null; timeMs: number | null; outcomes?: ReplayOutcome[] }

export function HistoricalVehicleDetails({ vehicle, timeMs, outcomes = [] }: Props) {
  const predictions = useDashboardStore((state) => state.replayPredictions)
  const failures = useDashboardStore((state) => state.replayFailures)
  if (!vehicle || timeMs === null) return <section className="historical-details"><span className="eyebrow">Выбранный транспорт</span><h2>Выберите машину</h2></section>

  const run = currentRun(vehicle, timeMs)
  const runStops = run ? vehicle.stops.filter((stop) => run.stop_ids.includes(stop.stop_id)) : []
  const point = currentPoint(vehicle, timeMs)
  const forecast = point ? predictions[point.sample_id] : undefined
  const outcomesById = new Map(outcomes.map((outcome) => [outcome.sample_id, outcome]))
  const completed = vehicle.points.flatMap((sample) => {
    const outcome = outcomesById.get(sample.sample_id)
    return outcome && janMs(sample.T) <= timeMs && janMs(outcome.actual_at) <= timeMs
      ? [{ sample, outcome }] : []
  })
  const lastActual = completed.at(-1) ?? null
  const upcoming = runStops.filter((stop) => janMs(stop.planned_at) >= timeMs - 3 * 60_000
    && janMs(stop.planned_at) <= timeMs + 25 * 60_000).slice(0, 8)
  const routeLabel = runStops.length > 1
    ? runStops[0]!.place_id === runStops.at(-1)!.place_id
      ? `Кольцевой маршрут · ${stopLabel(vehicle, runStops[0]!.stop_id)}`
      : `${stopLabel(vehicle, runStops[0]!.stop_id)} — ${stopLabel(vehicle, runStops.at(-1)!.stop_id)}`
    : 'Маршрут пока не определён'

  return <section className="historical-details">
    <span className="eyebrow">Выбранный транспорт</span>
    <h2>ТС {vehicle.tr_id}</h2>
    <p>Терминал {vehicle.unit_id}{run ? ` · рейс ${run.run_id}` : ''}</p>

    <div className="historical-priority">
      <div className={`historical-priority__forecast${forecast && forecast.predicted_delay_s >= 120 ? ' historical-priority__forecast--late' : ''}`}>
        <span>Прогноз через 10–15 мин</span>
        <strong>{point ? forecast ? signed(forecast.predicted_delay_s) : failures[point.sample_id] ? 'Недоступен' : 'Рассчитываем…' : 'Нет прогноза'}</strong>
        <small>{point ? `${stopLabel(vehicle, point.target_stop_id)} · ${forecast ? `ожидаем ${janClock(janMs(point.target_time_begin) + forecast.predicted_delay_s * 1000)} · ` : ''}план ${janClock(point.target_time_begin)}` : 'Нет ближайшей целевой остановки'}</small>
      </div>
      <div className="historical-priority__pair">
        <div><span>Текущее отклонение</span><strong>{point ? signed(point.cur_dev_s) : '—'}</strong></div>
        <div><span>Последняя фактическая остановка</span><strong>{lastActual ? signed(lastActual.outcome.actual_delay_s) : '—'}</strong><small>{lastActual ? `${stopLabel(vehicle, lastActual.sample.target_stop_id)} · ${janClock(lastActual.outcome.actual_at)}` : 'Факт прибытия пока не получен'}</small></div>
      </div>
    </div>

    <div className="historical-route-summary"><div><span>Маршрут</span><strong>{run ? routeLabel : 'Нет текущего рейса'}</strong></div>{run && <div><span>Время рейса</span><strong>{janClock(run.start_at)}–{janClock(run.end_at)}</strong></div>}</div>
    {upcoming.length > 0 && <div className="historical-stops"><strong>Ближайшие остановки · план</strong>{upcoming.map((stop) => <div key={stop.stop_id}><MapPin size={13} /><span>{janClock(stop.planned_at)}</span><span title={stop.address ?? undefined}>{stopLabel(vehicle, stop.stop_id)}</span></div>)}</div>}
    {run && <details className="historical-all-stops"><summary>Весь рейс · {runStops.length} остановок</summary><div>{runStops.map((stop) => <div key={stop.stop_id}><span>{janClock(stop.planned_at)}</span><span>{stopLabel(vehicle, stop.stop_id)}</span></div>)}</div></details>}
    {completed.length > 0 && <div className="historical-results"><strong>Прогноз и факт на пройденных остановках</strong>{completed.slice(-5).reverse().map(({ sample, outcome }) => <div key={sample.sample_id}><span>{stopLabel(vehicle, sample.target_stop_id)}</span><b>{predictions[sample.sample_id] ? signed(predictions[sample.sample_id]!.predicted_delay_s) : '—'} / {signed(outcome.actual_delay_s)}</b></div>)}</div>}
  </section>
}
