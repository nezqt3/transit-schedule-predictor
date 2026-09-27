import { formatDelay } from '@/lib/format/time'
import { useDashboardStore } from '@/store/dashboard'
import type { ReplayFleetVehicle, ReplayOutcome } from '@/types/replay'
import { currentPoint, currentRun, displaySpeedKmh, janClock, janMs, latestTelemetry, stopLabel } from './fleetClock'

type Props = { vehicle: ReplayFleetVehicle | null; timeMs: number | null; outcomes?: ReplayOutcome[] }

export function HistoricalVehicleDetails({ vehicle, timeMs, outcomes = [] }: Props) {
  const predictions = useDashboardStore((state) => state.replayPredictions)
  const failures = useDashboardStore((state) => state.replayFailures)
  if (!vehicle || timeMs === null) return <section className="historical-details"><span className="eyebrow">Выбранный транспорт</span><h2>Выберите машину</h2></section>

  const run = currentRun(vehicle, timeMs)
  const runStops = run ? vehicle.stops.filter((stop) => run.stop_ids.includes(stop.stop_id)) : []
  const point = currentPoint(vehicle, timeMs)
  const forecast = point ? predictions[point.sample_id] : undefined
  const gps = latestTelemetry(vehicle, timeMs)
  const speed = displaySpeedKmh(gps?.speed ?? null)
  const outcomesById = new Map(outcomes.map((outcome) => [outcome.sample_id, outcome]))
  const completed = vehicle.points.flatMap((sample) => {
    const outcome = outcomesById.get(sample.sample_id)
    return outcome && janMs(sample.T) <= timeMs && janMs(outcome.actual_at) <= timeMs
      ? [{ sample, outcome }] : []
  })
  const lastActual = completed.at(-1) ?? null
  const upcoming = runStops.filter((stop) => janMs(stop.planned_at) >= timeMs - 3 * 60_000
    && janMs(stop.planned_at) <= timeMs + 25 * 60_000).slice(0, 3)
  const routeLabel = runStops.length > 1
    ? runStops[0]!.place_id === runStops.at(-1)!.place_id
      ? `Кольцевой маршрут · ${stopLabel(vehicle, runStops[0]!.stop_id)}`
      : `${stopLabel(vehicle, runStops[0]!.stop_id)} — ${stopLabel(vehicle, runStops.at(-1)!.stop_id)}`
    : 'Маршрут пока не определён'

  return <section className="historical-details">
    <div className="vehicle-details__top"><div><span className="eyebrow">Январь · реальный рейс · терминал #{vehicle.unit_id}</span><h2>Трамвай #{vehicle.tr_id}</h2></div></div>
    <div className="vehicle-route"><span>Маршрут</span><strong>{run ? routeLabel : 'Нет текущего рейса'}</strong></div>
    <div className={`vehicle-forecast${forecast && forecast.predicted_delay_s >= 120 ? ' vehicle-forecast--high' : ''}`}>
      <div className="vehicle-forecast__heading"><span>Через 10–15 минут</span>{forecast && <span className={`vehicle-forecast__risk vehicle-forecast__risk--${forecast.predicted_delay_s >= 120 ? 'high' : 'low'}`}>{forecast.predicted_delay_s >= 120 ? 'Риск опоздания' : 'В графике'}</span>}</div>
      <strong className="vehicle-forecast__value">{point ? forecast ? formatDelay(forecast.predicted_delay_s) : failures[point.sample_id] ? 'Недоступен' : 'Рассчитываем…' : 'Нет прогноза'}</strong>
      {point ? <><span className="vehicle-forecast__stop">{stopLabel(vehicle, point.target_stop_id)}</span><div className="vehicle-forecast__times"><div><span>План</span><strong>{janClock(point.target_time_begin)}</strong></div><span aria-hidden>→</span><div><span>Ожидаем</span><strong>{forecast ? janClock(janMs(point.target_time_begin) + Math.round(forecast.predicted_delay_s) * 1000) : '—'}</strong></div></div></> : <span className="vehicle-forecast__reason">Нет остановки в горизонте прогноза</span>}
    </div>
    <div className="vehicle-metrics"><div><span>Сейчас</span><strong>{point ? formatDelay(point.cur_dev_s) : '—'}</strong><small>Отклонение по данным рейса</small></div><div><span>Последний факт</span><strong>{lastActual ? formatDelay(lastActual.outcome.actual_delay_s) : '—'}</strong><small>{lastActual ? `${stopLabel(vehicle, lastActual.sample.target_stop_id)} · ${janClock(lastActual.outcome.actual_at)}` : 'Ожидаем прибытие'}</small></div></div>
    <div className="vehicle-live-line"><span>GPS {gps ? janClock(gps.event_time) : '—'}</span><strong>{speed == null ? 'Скорость —' : `${speed.toFixed(0)} км/ч`}</strong></div>
    {upcoming.length > 0 && <div className="historical-stops"><strong>Дальше по маршруту</strong>{upcoming.map((stop) => <div key={stop.stop_id}><span>{janClock(stop.planned_at)}</span><span title={stop.address ?? undefined}>{stopLabel(vehicle, stop.stop_id)}</span></div>)}</div>}
    {run && <details className="historical-all-stops"><summary>Весь рейс · {runStops.length} остановок</summary><div>{runStops.map((stop) => <div key={stop.stop_id}><span>{janClock(stop.planned_at)}</span><span>{stopLabel(vehicle, stop.stop_id)}</span></div>)}</div></details>}
    {completed.length > 0 && <details className="historical-results"><summary>Прогноз / факт · {completed.length}</summary>{completed.slice(-5).reverse().map(({ sample, outcome }) => <div key={sample.sample_id}><span>{stopLabel(vehicle, sample.target_stop_id)}</span><b>{predictions[sample.sample_id] ? formatDelay(predictions[sample.sample_id]!.predicted_delay_s) : '—'} / {formatDelay(outcome.actual_delay_s)}</b></div>)}</details>}
  </section>
}
