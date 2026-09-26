import { AlertTriangle, ChevronLeft, ChevronRight, MapPin, Pause, Play, RotateCcw, Search } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'
import { Link } from 'react-router-dom'

import { predictReplayPoint, useReplayFleet, useReplayStreamStatus } from './api'
import { currentPoint, currentRun, janClock, janMs, latestTelemetry } from './fleetClock'
import { HistoricalFleetMap, type VisibleVehicle } from './HistoricalFleetMap'
import { useVehicleHistory } from '@/features/vehicles/api'
import { useVehicleFeed } from '@/features/vehicles/hooks'
import { fleetStatusIcons } from '@/features/vehicles/markerIcon'
import { eventTimeMs, hasValidPosition } from '@/lib/telemetry/readEvent'
import { statusLabel, vehicleStatus, type VehicleStatus } from '@/lib/telemetry/vehicleStatus'
import type { TelemetryEvent } from '@/types/api'
import type { ReplayPrediction } from '@/types/replay'

const signed = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(0)} с`
const LATE_THRESHOLD_S = 120
type FleetFilter = 'all' | 'attention' | VehicleStatus

const filterOptions: { value: FleetFilter; label: string }[] = [
  { value: 'all', label: 'Все состояния' },
  { value: 'attention', label: 'Требуют внимания' },
  { value: 'alarm', label: 'Тревога' },
  { value: 'stale', label: 'Устарели координаты' },
  { value: 'moving', label: 'В движении' },
  { value: 'stopped', label: 'Стоят' },
  { value: 'no-position', label: 'Нет координат' },
  { value: 'unknown', label: 'Скорость неизвестна' },
]

export function HistoricalFleetDashboard() {
  const { data: fleet, isPending, isError } = useReplayFleet()
  const { data: streamStatus } = useReplayStreamStatus()
  const { data: ndtpEvents = [] } = useVehicleFeed()
  const [timeMs, setTimeMs] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [followNdtp, setFollowNdtp] = useState(false)
  const [speed, setSpeed] = useState(600)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [showAllRoutes, setShowAllRoutes] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(390)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FleetFilter>('all')
  const [predictions, setPredictions] = useState<Record<string, ReplayPrediction>>({})
  const [failures, setFailures] = useState<Record<string, string>>({})
  const requested = useRef(new Set<string>())
  const inFlight = useRef(0)

  const resizeSidebar = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    const onMove = (moveEvent: PointerEvent) => {
      const maximum = Math.min(620, Math.max(280, window.innerWidth * .48))
      setSidebarWidth(Math.min(maximum, Math.max(280, moveEvent.clientX)))
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      document.body.classList.remove('is-resizing-sidebar')
    }
    document.body.classList.add('is-resizing-sidebar')
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  const startMs = fleet ? janMs(fleet.start_at) : 0
  const endMs = fleet ? janMs(fleet.end_at) : 0
  const selected = fleet?.vehicles.find((vehicle) => vehicle.tr_id === selectedId) ?? null
  const { data: ndtpHistory } = useVehicleHistory(followNdtp ? selected?.unit_id ?? null : null)
  useEffect(() => {
    if (!fleet) return
    const morning = janMs('2026-01-06T08:00:00')
    setTimeMs(Math.min(Math.max(morning, janMs(fleet.start_at)), janMs(fleet.end_at)))
  }, [fleet])

  useEffect(() => {
    if (!followNdtp || streamStatus?.time_mode !== 'original' || !streamStatus.source_at || !fleet) return
    setTimeMs(Math.min(Math.max(janMs(streamStatus.source_at), startMs), endMs))
  }, [followNdtp, streamStatus, fleet, startMs, endMs])

  useEffect(() => {
    if (!playing || !fleet) return
    const timer = window.setInterval(() => {
      setTimeMs((current) => Math.min(current + 200 * speed, endMs))
    }, 200)
    return () => window.clearInterval(timer)
  }, [playing, speed, endMs, fleet])
  useEffect(() => {
    if (playing && timeMs >= endMs && endMs > 0) setPlaying(false)
  }, [playing, timeMs, endMs])

  // Each request uses its own original January T. Playback speed changes only presentation.
  useEffect(() => {
    if (!fleet || timeMs < startMs) return
    const capacity = Math.max(0, 6 - inFlight.current)
    if (!capacity) return
    const due = fleet.vehicles.flatMap((vehicle) => vehicle.points)
      .filter((point) => janMs(point.T) <= timeMs && !requested.current.has(point.sample_id))
      .sort((a, b) => janMs(a.T) - janMs(b.T))
      .slice(0, capacity)
    for (const point of due) {
      requested.current.add(point.sample_id)
      inFlight.current += 1
      predictReplayPoint(point.sample_id)
        .then((value) => setPredictions((current) => ({ ...current, [point.sample_id]: value })))
        .catch((error: Error) => setFailures((current) => ({ ...current, [point.sample_id]: error.message })))
        .finally(() => { inFlight.current -= 1 })
    }
  }, [fleet, timeMs, startMs, predictions, failures])

  const visible = useMemo(() => {
    if (!fleet || !timeMs) return []
    const result: VisibleVehicle[] = []
    const byUnit = new Map(ndtpEvents.map((event) => [event.unit_id, event]))
    for (const vehicle of fleet.vehicles) {
      const event = followNdtp ? byUnit.get(vehicle.unit_id) : undefined
      const eventMs = event ? eventTimeMs(event) : 0
      if (followNdtp && (!event || eventMs > timeMs || timeMs - eventMs > 5 * 60_000)) continue
      const gps = event
        ? hasValidPosition(event) && event.nav ? {
          available_at: new Date(eventMs).toISOString(),
          event_time: new Date(eventMs).toISOString(),
          lat: event.nav.latitude, lon: event.nav.longitude,
          speed: event.nav.speed_avg, heading: event.nav.course,
        } : null
        : latestTelemetry(vehicle, timeMs)
      if (!followNdtp && !gps) continue
      const status: VehicleStatus = event ? vehicleStatus(event, timeMs)
        : gps && timeMs - janMs(gps.available_at) > 30_000 ? 'stale'
          : gps?.speed === null ? 'unknown' : gps && gps.speed > 2 ? 'moving' : 'stopped'
      const point = currentPoint(vehicle, timeMs)
      const forecast = point ? predictions[point.sample_id] : undefined
      result.push({ vehicle, gps, status, late: Boolean(forecast && forecast.predicted_delay_s >= LATE_THRESHOLD_S) })
    }
    return result.sort((a, b) => Number(b.late) - Number(a.late) || a.vehicle.tr_id - b.vehicle.tr_id)
  }, [fleet, timeMs, predictions, followNdtp, ndtpEvents])
  const filteredVisible = useMemo(() => visible.filter((item) => {
    const matchesSearch = String(item.vehicle.tr_id).includes(query.trim())
    const matchesState = filter === 'all'
      || filter === item.status
      || (filter === 'attention' && ['alarm', 'stale', 'no-position'].includes(item.status))
    return matchesSearch && matchesState
  }), [visible, query, filter])
  const selectedVisible = filteredVisible.find((item) => item.vehicle.tr_id === selectedId)

  const receivedTrack = useMemo(() => followNdtp ? (ndtpHistory ?? []).flatMap((event: TelemetryEvent) => {
    if (!hasValidPosition(event) || !event.nav || eventTimeMs(event) > timeMs) return []
    const eventMs = eventTimeMs(event)
    return [{ available_at: new Date(eventMs).toISOString(), event_time: new Date(eventMs).toISOString(),
      lat: event.nav.latitude, lon: event.nav.longitude, speed: event.nav.speed_avg,
      heading: event.nav.course }]
  }) : null, [followNdtp, ndtpHistory, timeMs])

  useEffect(() => {
    if (!filteredVisible.length) {
      if (selectedId !== null) setSelectedId(null)
      return
    }
    if (selectedId === null || !filteredVisible.some((item) => item.vehicle.tr_id === selectedId)) {
      const withDelay = filteredVisible.find((item) => {
        const point = currentPoint(item.vehicle, timeMs)
        return point && point.cur_dev_s >= LATE_THRESHOLD_S
      })
      const withForecast = filteredVisible.find((item) => currentPoint(item.vehicle, timeMs))
      setSelectedId((withDelay ?? withForecast ?? filteredVisible[0]!).vehicle.tr_id)
    }
  }, [filteredVisible, selectedId, timeMs])

  const selectVehicle = useCallback((trId: number) => setSelectedId(trId), [])
  const selectedRun = selected ? currentRun(selected, timeMs) : null
  const runStops = selectedRun && selected ? selected.stops.filter((stop) =>
    selectedRun.stop_ids.includes(stop.stop_id)) : []
  const selectedPoint = selected ? currentPoint(selected, timeMs) : null
  const selectedForecast = selectedPoint ? predictions[selectedPoint.sample_id] : undefined
  const selectedCompleted = selected?.points.findLast((point) =>
    janMs(point.T) <= timeMs && janMs(point.actual_at) <= timeMs) ?? null
  const selectedResult = selectedCompleted ? predictions[selectedCompleted.sample_id] : undefined
  const recentStops = selected?.points.filter((point) =>
    janMs(point.T) <= timeMs && janMs(point.actual_at) <= timeMs).slice(-5).reverse() ?? []
  const nextStops = selectedRun ? runStops.filter((stop) =>
    janMs(stop.planned_at) >= timeMs - 3 * 60_000 &&
    janMs(stop.planned_at) <= timeMs + 25 * 60_000).slice(0, 8) : []

  const allPoints = fleet?.vehicles.flatMap((vehicle) => vehicle.points) ?? []
  const dueCount = allPoints.filter((point) => janMs(point.T) <= timeMs).length
  const evaluated = allPoints.filter((point) => predictions[point.sample_id] && janMs(point.actual_at) <= timeMs)
  const mae = (baseline: boolean) => evaluated.length
    ? evaluated.reduce((sum, point) => sum + Math.abs(
      (baseline ? point.cur_dev_s : predictions[point.sample_id]!.predicted_delay_s) - point.actual_delay_s,
    ), 0) / evaluated.length : null
  const validRuns = fleet?.vehicles.reduce((sum, vehicle) => sum + vehicle.runs.filter((run) => run.valid).length, 0) ?? 0
  const activeRoutes = filteredVisible.filter((item) => currentRun(item.vehicle, timeMs)).length

  if (isPending) return <div className="historical-loading">Загружаем январские GPS, остановки и рейсы…</div>
  if (isError || !fleet) return <div className="historical-loading">Не удалось загрузить январские данные из backend.</div>

  return (
    <div className={`historical-dashboard${detailsOpen ? '' : ' historical-dashboard--details-collapsed'}`} style={{ '--sidebar-width': `${sidebarWidth}px` } as CSSProperties}>
      <aside className="historical-sidebar">
        <div className="historical-sidebar__head">
          <span className="eyebrow">6 января 2026 · запись</span>
          <h1>Транспорт на линии</h1>
          <p>{filteredVisible.length}{filteredVisible.length !== visible.length ? ` из ${visible.length}` : ''} машин в момент {janClock(timeMs)} · {activeRoutes} на подтверждённых маршрутах · {followNdtp ? 'пакеты Backend NDTP' : 'CSV запись'}</p>
          <div className="historical-sidebar__filters">
            <label className="fleet-search"><Search aria-hidden size={18} /><input aria-label="Поиск по ID транспорта" inputMode="numeric" onChange={(event) => setQuery(event.target.value)} placeholder="Поиск по ID транспорта" value={query} /></label>
            <label className="fleet-filter"><span className="sr-only">Фильтр по состоянию</span><select onChange={(event) => setFilter(event.target.value as FleetFilter)} value={filter}>{filterOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
          </div>
        </div>
        <div className="historical-fleet-list">
          {filteredVisible.map(({ vehicle, gps, status, late }) => {
            const run = currentRun(vehicle, timeMs)
            const point = currentPoint(vehicle, timeMs)
            const forecast = point ? predictions[point.sample_id] : undefined
            const Icon = fleetStatusIcons[status]
            return <button className={`historical-vehicle${vehicle.tr_id === selectedId ? ' historical-vehicle--selected' : ''}`} key={vehicle.tr_id} onClick={() => setSelectedId(vehicle.tr_id)} type="button">
              <span aria-hidden className={`fleet-row__icon fleet-row__icon--${status}`}><Icon size={19} strokeWidth={2.5} /></span>
              <span className="historical-vehicle__text"><strong>ТС {vehicle.tr_id} {late && <span className="historical-vehicle__late" title="Прогноз опоздания">!</span>}</strong><small>{statusLabel[status]} · {run ? `рейс ${run.run_id} · ${run.confirmed_stops}/${run.stop_ids.length} точек GPS` : 'маршрут не подтверждён'}</small></span>
              <span className="historical-vehicle__value">{forecast ? signed(forecast.predicted_delay_s) : gps?.speed == null ? '—' : `${gps.speed.toFixed(0)} км/ч`}</span>
            </button>
          })}
          {!filteredVisible.length && <p className="fleet-list__message">{visible.length ? 'По выбранному поиску и фильтру транспорта нет.' : followNdtp ? 'Пока нет подходящих январских NDTP-пакетов в Backend.' : 'В это время свежих GPS-пакетов нет. Переместите ползунок.'}</p>}
        </div>
      </aside>

      <div aria-label="Изменить ширину списка транспорта" aria-valuemax={620} aria-valuemin={280} aria-valuenow={sidebarWidth} className="sidebar-resizer" onDoubleClick={() => setSidebarWidth(sidebarWidth === 280 ? 620 : 280)} onPointerDown={resizeSidebar} role="separator" title="Перетащите, чтобы изменить ширину списка. Двойной щелчок — минимум/максимум." />

      <aside className="historical-details-panel">
        <button aria-expanded={detailsOpen} className="details-panel__toggle" onClick={() => setDetailsOpen(!detailsOpen)} title={detailsOpen ? 'Свернуть статистику' : 'Развернуть статистику'} type="button">
          {detailsOpen ? <ChevronRight size={21} strokeWidth={2.5} /> : <ChevronLeft size={21} strokeWidth={2.5} />}
          <span className="sr-only">{detailsOpen ? 'Свернуть статистику' : 'Развернуть статистику'}</span>
        </button>
        {detailsOpen && <section className="historical-details">
          <span className="eyebrow">Выбранный транспорт</span>
          <h2>{selected ? `ТС ${selected.tr_id}` : 'Выберите машину'}</h2>
          {selected && <>
            <p>Терминал {selected.unit_id} · {selectedVisible?.status === 'no-position' ? 'последний пакет без валидных координат' : selectedRun ? `рейс ${selectedRun.run_id}` : 'GPS-след без подтверждённого плана остановок'}</p>
            {selectedRun && <div className="historical-fact"><span>Маршрут</span><strong>{selectedRun.confirmed_stops} из {selectedRun.stop_ids.length} точек рядом с GPS</strong></div>}
            {selectedRun && <div className="historical-fact"><span>Время рейса</span><strong>{janClock(selectedRun.start_at)}–{janClock(selectedRun.end_at)}</strong></div>}
            <div className="historical-fact"><span>Прогноз на 10–15 мин</span><strong className={selectedForecast && selectedForecast.predicted_delay_s >= LATE_THRESHOLD_S ? 'historical-late' : ''}>{selectedPoint ? selectedForecast ? signed(selectedForecast.predicted_delay_s) : failures[selectedPoint.sample_id] ? 'Ошибка ML' : 'Рассчитываем…' : 'Нет точки прогноза'}</strong></div>
            {selectedPoint && <div className="historical-fact"><span>Целевая остановка</span><strong>#{selectedPoint.target_stop_id} · {janClock(selectedPoint.target_time_begin)}</strong></div>}
            {selectedPoint && <div className="historical-fact"><span>Текущее отклонение в T</span><strong>{signed(selectedPoint.cur_dev_s)}</strong></div>}
            {selectedForecast && <div className="historical-fact"><span>Модель</span><strong>{selectedForecast.model_version}</strong></div>}
            {selectedCompleted && <div className="historical-fact"><span>Последняя проверенная остановка</span><strong>#{selectedCompleted.target_stop_id}: {selectedResult ? `${signed(selectedResult.predicted_delay_s)} / факт ${signed(selectedCompleted.actual_delay_s)}` : 'факт доступен, прогноз считается'}</strong></div>}
            {selectedPoint && failures[selectedPoint.sample_id] && <button className="historical-retry" onClick={() => { requested.current.delete(selectedPoint.sample_id); setFailures((current) => { const copy = { ...current }; delete copy[selectedPoint.sample_id]; return copy }) }} type="button">Повторить прогноз</button>}
            {nextStops.length > 0 && <div className="historical-stops"><strong>Ближайшие точки маршрута</strong>{nextStops.map((stop) => <div key={stop.stop_id}><MapPin size={13} /><span>{janClock(stop.planned_at)}</span><span title={stop.address ?? undefined}>{stop.address ?? `Точка #${stop.stop_id}`}</span><b title={stop.gps_confirmed ? `GPS в ${stop.gps_distance_m} м` : 'GPS рядом не найден'}>{stop.gps_confirmed ? '●' : '○'}</b></div>)}</div>}
            {selectedRun && <details className="historical-all-stops"><summary>Весь рейс · {runStops.length} точек</summary><div>{runStops.map((stop) => <div key={stop.stop_id}><span>{janClock(stop.planned_at)}</span><span>{stop.address ?? `Точка #${stop.stop_id}`}</span><b>{stop.gps_confirmed ? '●' : '○'}</b></div>)}</div></details>}
            {recentStops.length > 0 && <div className="historical-results"><strong>Прогноз / факт на остановках</strong>{recentStops.map((point) => <div key={point.sample_id}><span>#{point.target_stop_id}</span><span>{janClock(point.target_time_begin)}</span><b>{predictions[point.sample_id] ? signed(predictions[point.sample_id]!.predicted_delay_s) : '…'} / {signed(point.actual_delay_s)}</b></div>)}<Link to={`/replay?tr_id=${selected.tr_id}`}>Все точки и ошибки →</Link></div>}
          </>}
        </section>}
      </aside>

      <main className="historical-main">
        <div className="historical-toolbar">
          <div className="historical-toolbar__title"><span className="eyebrow">Общие часы записи · МСК</span><strong>{janClock(timeMs)}</strong></div>
          <button className={followNdtp ? 'historical-toolbar__following' : ''} disabled={!followNdtp && (streamStatus?.state !== 'running' || streamStatus?.time_mode !== 'original' || !streamStatus?.source_at)} onClick={() => { setPlaying(false); if (!followNdtp && streamStatus?.source_at) setTimeMs(janMs(streamStatus.source_at)); setFollowNdtp(!followNdtp) }} title="Показывать пакеты, реально принятые Backend из январского NDTP-потока" type="button">{followNdtp ? `● NDTP ${streamStatus?.speed_multiplier ?? 1}×` : 'Следовать NDTP'}</button>
          <button aria-label={playing ? 'Пауза' : 'Воспроизвести'} disabled={followNdtp || timeMs >= endMs} onClick={() => setPlaying(!playing)} type="button">{playing ? <Pause size={18} /> : <Play size={18} />}{playing ? 'Пауза' : 'Пуск'}</button>
          <button disabled={followNdtp} onClick={() => { setPlaying(false); setTimeMs(startMs) }} title="К началу суток" type="button"><RotateCcw size={17} /> С начала</button>
          <label>Скорость {followNdtp ? <strong>{streamStatus?.speed_multiplier ?? 1}× NDTP</strong> : <select onChange={(event) => setSpeed(Number(event.target.value))} value={speed}><option value={1}>1×</option><option value={60}>60×</option><option value={300}>300×</option><option value={600}>600×</option><option value={1800}>1800×</option></select>}</label>
          <label className="historical-toolbar__routes"><input checked={showAllRoutes} onChange={(event) => setShowAllRoutes(event.target.checked)} type="checkbox" /> Все активные маршруты</label>
        </div>
        <div className="historical-timeline"><span>{janClock(startMs)}</span><input aria-label="Общий момент январской записи" disabled={followNdtp} max={endMs} min={startMs} onChange={(event) => { setPlaying(false); setTimeMs(Number(event.target.value)) }} step={1000} type="range" value={Math.min(Math.max(timeMs, startMs), endMs)} /><span>{janClock(endMs)}</span></div>
        <div className="historical-stats"><span><strong>{visible.filter((item) => item.gps).length}</strong> активных GPS</span><span><strong>{validRuns}</strong> подтверждённых проходов</span><span><strong>{Object.keys(predictions).length}/{dueCount}</strong> прогнозов к T</span><span><strong>{mae(false)?.toFixed(1) ?? '—'}</strong> MAE модели, с</span><span><strong>{mae(true)?.toFixed(1) ?? '—'}</strong> MAE cur_dev, с</span></div>
        <div className="historical-map-wrap">
          <HistoricalFleetMap onSelect={selectVehicle} receivedTrack={receivedTrack} selected={selected} showAllRoutes={showAllRoutes} timeMs={timeMs} visible={filteredVisible} />
          <div className="historical-map-legend"><span>↗ Движется · ■ Стоит · ◷ GPS устарел</span><span><AlertTriangle size={13} /> Прогноз ≥2 мин</span><span>— GPS уже пройден</span><span>┄ Плановый маршрут</span><span>● GPS-подтверждённая точка</span></div>
        </div>
        <p className="historical-note">{followNdtp ? 'Позиции и GPS-след выбранной машины взяты из пакетов, принятых Backend по NDTP. ' : 'Позиции взяты из январского CSV по времени получения. '}Расписание и точки ML взяты из январских CSV; исходное T не сдвигается. Номер общественного маршрута, тревоги и CAN-датчики в записи отсутствуют. MAE этого дня — диагностика, не независимая оценка: train и test относятся к одним суткам. Из 30 терминалов валидный GPS есть у 23.</p>
      </main>
    </div>
  )
}
