import { AlertTriangle, BusFront, ChevronLeft, ChevronRight, Pause, Play, RotateCcw, Search, SkipBack, SkipForward } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'

import { fleetStatusIcons } from '@/features/vehicles/markerIcon'
import { WhatIfPanel } from '@/features/what-if/WhatIfPanel'
import { statusLabel, type VehicleStatus } from '@/lib/telemetry/vehicleStatus'
import { useDashboardStore } from '@/store/dashboard'
import { useReplayFleet, useReplayOutcomes } from './api'
import { displaySpeedKmh, fleetSnapshot, janClock, replayBounds } from './fleetClock'
import { HistoricalFleetMap } from './HistoricalFleetMap'
import { HistoricalVehicleDetails } from './HistoricalVehicleDetails'

const signed = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(0)} с`
type FleetFilter = 'all' | 'attention' | VehicleStatus

const filterOptions: { value: FleetFilter; label: string }[] = [
  { value: 'all', label: 'Все состояния' },
  { value: 'attention', label: 'Требуют внимания' },
  { value: 'stale', label: 'Устарели координаты' },
  { value: 'moving', label: 'В движении' },
  { value: 'stopped', label: 'Стоят' },
  { value: 'unknown', label: 'Скорость неизвестна' },
]

export function HistoricalFleetDashboard() {
  const { data: fleet, isPending, isError } = useReplayFleet()
  const timeMs = useDashboardStore((state) => state.replayTimeMs)
  const playing = useDashboardStore((state) => state.replayPlaying)
  const playbackSpeed = useDashboardStore((state) => state.replaySpeed)
  const setReplayTime = useDashboardStore((state) => state.setReplayTime)
  const setReplayPlaying = useDashboardStore((state) => state.setReplayPlaying)
  const setReplaySpeed = useDashboardStore((state) => state.setReplaySpeed)
  const { data: outcomes = [] } = useReplayOutcomes(timeMs)
  const predictions = useDashboardStore((state) => state.replayPredictions)
  const selectedId = useDashboardStore((state) => state.selectedReplayId)
  const selectVehicle = useDashboardStore((state) => state.selectReplayVehicle)
  const [sidebarWidth, setSidebarWidth] = useState(390)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FleetFilter>('all')
  const [whatIfOpen, setWhatIfOpen] = useState(false)

  const visible = useMemo(() => fleetSnapshot(fleet, timeMs, predictions), [fleet, timeMs, predictions])
  const filtered = useMemo(() => visible.filter((item) => {
    const matchesSearch = String(item.vehicle.tr_id).includes(query.trim())
    const matchesState = filter === 'all' || filter === item.status
      || (filter === 'attention' && (item.late || item.status === 'stale'))
    return matchesSearch && matchesState
  }), [visible, query, filter])
  const selected = fleet?.vehicles.find((vehicle) => vehicle.tr_id === selectedId) ?? null
  const attentionCount = visible.filter((item) => item.late || item.status === 'stale').length
  const whatIfVehicles = visible.flatMap((item) => item.forecast && item.run && item.point ? [{
    tr_id: item.vehicle.tr_id,
    predicted_delay_s: item.forecast.predicted_delay_s,
    run_id: item.run.run_id,
    target_stop_id: item.point.target_stop_id,
  }] : [])

  useEffect(() => {
    if (!visible.length && selectedId !== null) { selectVehicle(null); return }
    if (visible.length && !visible.some((item) => item.vehicle.tr_id === selectedId)) {
      selectVehicle((visible.find((item) => item.late) ?? visible[0]!).vehicle.tr_id)
    }
  }, [selectedId, visible, selectVehicle])

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
  const onMapSelect = useCallback((trId: number) => selectVehicle(trId), [selectVehicle])

  if (isPending) return <div className="historical-loading">Подключаем транспорт…</div>
  if (isError || !fleet) return <div className="historical-loading">Не удалось получить данные транспорта.</div>

  const { startMs, endMs } = replayBounds(fleet)
  const currentTimeMs = Math.min(endMs, Math.max(startMs, timeMs ?? startMs))
  const seekBy = (deltaMs: number) => setReplayTime(Math.min(endMs, Math.max(startMs, currentTimeMs + deltaMs)))
  const togglePlayback = () => {
    if (!playing && currentTimeMs >= endMs) setReplayTime(startMs)
    setReplayPlaying(!playing)
  }

  return <div className={`historical-dashboard${detailsOpen ? '' : ' historical-dashboard--details-collapsed'}`} style={{ '--sidebar-width': `${sidebarWidth}px` } as CSSProperties}>
    <aside className="historical-sidebar">
      <div className="historical-sidebar__head">
        <div className="historical-sidebar__title"><h1>Транспорт на линии</h1><span>{visible.length}</span></div>
        <div className="historical-sidebar__filters">
          <label className="fleet-search"><Search aria-hidden size={18} /><input aria-label="Поиск по ID транспорта" inputMode="numeric" onChange={(event) => setQuery(event.target.value)} placeholder="Поиск по ID транспорта" value={query} /></label>
          <label className="fleet-filter"><span className="sr-only">Фильтр по состоянию</span><select onChange={(event) => setFilter(event.target.value as FleetFilter)} value={filter}>{filterOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        </div>
      </div>
      <div className="historical-fleet-list">
        {filtered.map(({ vehicle, gps, status, late, run, forecast }) => {
          const Icon = fleetStatusIcons[status]
          const speed = displaySpeedKmh(gps?.speed ?? null)
          return <button aria-current={vehicle.tr_id === selectedId ? 'true' : undefined} className={`historical-vehicle${vehicle.tr_id === selectedId ? ' historical-vehicle--selected' : ''}`} key={vehicle.tr_id} onClick={() => selectVehicle(vehicle.tr_id)} type="button">
            <span aria-hidden className={`fleet-row__icon fleet-row__icon--${status}`}><Icon size={19} strokeWidth={2.5} /></span>
            <span className="historical-vehicle__text"><strong>ТС {vehicle.tr_id} {late && <span className="historical-vehicle__late" title="Прогноз опоздания">!</span>}</strong><small>{statusLabel[status]}{run ? ` · рейс ${run.run_id}` : ''}</small></span>
            <span className="historical-vehicle__value">{forecast ? signed(forecast.predicted_delay_s) : speed === null ? '—' : `${speed.toFixed(0)} км/ч`}</span>
          </button>
        })}
        {!filtered.length && <p className="fleet-list__message">{visible.length ? 'По выбранному фильтру транспорта нет.' : 'Ожидаем транспорт на линии.'}</p>}
      </div>
    </aside>

    <div aria-label="Изменить ширину списка транспорта" aria-valuemax={620} aria-valuemin={280} aria-valuenow={sidebarWidth} className="sidebar-resizer" onDoubleClick={() => setSidebarWidth(sidebarWidth === 280 ? 620 : 280)} onPointerDown={resizeSidebar} role="separator" title="Перетащите, чтобы изменить ширину списка." />

    <aside className="historical-details-panel">
      <button aria-expanded={detailsOpen} className="details-panel__toggle" onClick={() => setDetailsOpen(!detailsOpen)} title={detailsOpen ? 'Свернуть сведения' : 'Развернуть сведения'} type="button">
        {detailsOpen ? <ChevronRight size={21} strokeWidth={2.5} /> : <ChevronLeft size={21} strokeWidth={2.5} />}
        <span className="sr-only">{detailsOpen ? 'Свернуть сведения' : 'Развернуть сведения'}</span>
      </button>
      {detailsOpen && <HistoricalVehicleDetails vehicle={selected} timeMs={timeMs} outcomes={outcomes} />}
    </aside>

    <main className="historical-main">
      <div className="historical-overview"><span><strong>{visible.length}</strong> на карте</span><span><strong>{attentionCount}</strong> требуют внимания</span><button aria-pressed={whatIfOpen} className="historical-overview__what-if" onClick={() => setWhatIfOpen(!whatIfOpen)} type="button"><BusFront size={15} /> What-if</button></div>
      <div className="historical-playback" aria-label="Управление январской записью">
        <button aria-label="В начало записи" onClick={() => { setReplayPlaying(false); setReplayTime(startMs) }} title="В начало записи" type="button"><RotateCcw size={16} /></button>
        <button aria-label="Назад на 10 минут" onClick={() => seekBy(-10 * 60_000)} title="Назад на 10 минут" type="button"><SkipBack size={17} /></button>
        <button aria-label={playing ? 'Пауза' : 'Продолжить'} className="historical-playback__primary" onClick={togglePlayback} type="button">{playing ? <Pause size={17} /> : <Play size={17} />}{playing ? 'Пауза' : 'Продолжить'}</button>
        <button aria-label="Вперёд на 10 минут" onClick={() => seekBy(10 * 60_000)} title="Вперёд на 10 минут" type="button"><SkipForward size={17} /></button>
        <strong className="historical-playback__clock">{janClock(currentTimeMs)}</strong>
        <input aria-label="Промотка январской записи" max={endMs} min={startMs} onChange={(event) => setReplayTime(Number(event.target.value))} onPointerDown={() => setReplayPlaying(false)} step={1000} type="range" value={currentTimeMs} />
        <label>Скорость<select aria-label="Скорость воспроизведения" onChange={(event) => setReplaySpeed(Number(event.target.value))} value={playbackSpeed}><option value={1}>1×</option><option value={10}>10×</option><option value={60}>60×</option><option value={300}>300×</option><option value={600}>600×</option></select></label>
      </div>
      <div className="historical-map-wrap">
        <HistoricalFleetMap onSelect={onMapSelect} selected={selected} timeMs={timeMs ?? 0} visible={filtered} />
        {whatIfOpen && <WhatIfPanel context={timeMs === null ? 'Исторический поток' : `6 января · ${new Date(timeMs).toLocaleTimeString('ru-RU', { timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit' })}`} onClose={() => setWhatIfOpen(false)} vehicles={whatIfVehicles} />}
        <div className="historical-map-legend"><span>↗ Движется</span><span>■ Стоит</span><span>◷ GPS устарел</span><span><AlertTriangle size={13} /> Прогноз опоздания</span><span>— Пройденный путь</span><span>┄ Маршрут</span></div>
      </div>
    </main>
  </div>
}
