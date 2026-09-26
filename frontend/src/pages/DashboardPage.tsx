import { AlertTriangle, ArrowRight, ChevronLeft, ChevronRight, Clock3, MapPinOff, Navigation2, Search, Square, WifiOff } from 'lucide-react'
import { useEffect, useMemo, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'

import { useVehicleHistory } from '@/features/vehicles/api'
import { usePredictions } from '@/features/predictions/api'
import { VehicleMap } from '@/features/vehicles/VehicleMap'
import { fleetStatusIcons } from '@/features/vehicles/markerIcon'
import { useVehicleFeed } from '@/features/vehicles/hooks'
import { formatAge, formatClock } from '@/lib/format/time'
import { eventTimeMs, hasValidPosition, isStale, speedKmh } from '@/lib/telemetry/readEvent'
import { hasAlarm, needsAttention, statusLabel, vehicleStatus, type VehicleStatus } from '@/lib/telemetry/vehicleStatus'
import { useTelemetryStore } from '@/store/telemetry'
import { HistoricalFleetDashboard } from '@/features/replay/HistoricalFleetDashboard'
import { useDashboardStore } from '@/store/dashboard'
import type { StoredPrediction, TelemetryEvent } from '@/types/api'

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

function matchesFilter(event: TelemetryEvent, filter: FleetFilter, now: number) {
  if (filter === 'all') return true
  if (filter === 'attention') return needsAttention(event, now)
  if (filter === 'alarm') return hasAlarm(event)
  if (filter === 'stale') return isStale(event, now)
  if (filter === 'no-position') return !hasValidPosition(event)
  return vehicleStatus(event, now) === filter
}

function FleetRow({ event, selected, onSelect }: {
  event: TelemetryEvent
  selected: boolean
  onSelect: () => void
}) {
  const status = vehicleStatus(event)
  const Icon = fleetStatusIcons[status]
  const speed = speedKmh(event)
  return (
    <button
      aria-current={selected ? 'true' : undefined}
      className={`fleet-row${selected ? ' fleet-row--selected' : ''}`}
      onClick={onSelect}
      type="button"
    >
      <span aria-hidden className={`fleet-row__icon fleet-row__icon--${status}`}><Icon size={19} strokeWidth={2.5} /></span>
      <span className="fleet-row__main">
        <strong>#{event.unit_id}</strong>
        <small>{statusLabel[status]} · {formatAge(eventTimeMs(event))} назад</small>
      </span>
      {speed !== null && <span className="fleet-row__speed">{speed.toFixed(0)} <small>км/ч</small></span>}
      <ArrowRight aria-hidden size={16} className="fleet-row__arrow" />
    </button>
  )
}

export function VehicleDetails({ event, prediction }: {
  event: TelemetryEvent | undefined
  prediction: StoredPrediction | undefined
}) {
  if (!event) {
    return <div className="vehicle-details vehicle-details--empty"><strong>Выберите терминал</strong><span>Данные появятся здесь после выбора в списке или на карте.</span></div>
  }

  const status = vehicleStatus(event)
  const speed = speedKmh(event)
  return (
    <section aria-label={`Данные терминала ${event.unit_id}`} className="vehicle-details">
      <div className="vehicle-details__top">
        <div><span className="eyebrow">Выбранный терминал</span><h2>#{event.unit_id}</h2></div>
        <span className={`state-pill state-pill--${status}`}>{statusLabel[status]}</span>
      </div>
      <div className="historical-priority">
        <div className="historical-priority__forecast">
          <span>Прогноз через 10–15 мин</span>
          <strong>{prediction ? `${prediction.predicted_delay_s > 0 ? '+' : ''}${prediction.predicted_delay_s.toFixed(0)} с` : 'Нет прогноза'}</strong>
          <small>{prediction ? `Ожидаем прибытие ${formatClock(Date.parse(prediction.target_time) + prediction.predicted_delay_s * 1000)}` : 'Расписание и отклонение пока не получены'}</small>
        </div>
      </div>
      <div className="vehicle-details__facts">
        <div><span>Состояние</span><strong>{statusLabel[status]}</strong></div>
        <div><span>Скорость</span><strong>{speed === null ? '—' : `${speed.toFixed(1)} км/ч`}</strong></div>
        <div><span>Последнее обновление</span><strong>{formatClock(event.received_at)}</strong></div>
      </div>
      {isStale(event) && <p className="vehicle-details__note"><Clock3 size={15} /> Координаты устарели; положение на карте может быть неточным.</p>}
    </section>
  )
}

function LiveDashboard() {
  const { data: events = [], isPending, isError, dataUpdatedAt, streamConnected } = useVehicleFeed()
  const { data: predictions = [] } = usePredictions()
  const selectedUnitId = useTelemetryStore((state) => state.selectedUnitId)
  const selectUnit = useTelemetryStore((state) => state.selectUnit)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FleetFilter>('all')
  const [sidebarWidth, setSidebarWidth] = useState(390)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const now = Date.now()

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

  const filtered = useMemo(() => events.filter((event) => {
    const matchesSearch = String(event.unit_id).includes(query.trim())
    return matchesSearch && matchesFilter(event, filter, now)
  }), [events, filter, query, now])

  useEffect(() => {
    if (filtered.length === 0) {
      if (selectedUnitId !== null) selectUnit(null)
    } else if (!filtered.some((event) => event.unit_id === selectedUnitId)) {
      selectUnit(filtered[0]!.unit_id)
    }
  }, [filtered, selectedUnitId, selectUnit])

  const selectedEvent = filtered.find((event) => event.unit_id === selectedUnitId)
  const { data: selectedHistory = [] } = useVehicleHistory(selectedUnitId)
  const selectedPrediction = predictions.find((prediction) => prediction.unit_id === selectedUnitId)
  const attention = filtered.filter((event) => needsAttention(event, now))
  const rest = filtered.filter((event) => !needsAttention(event, now))
  const onMap = events.filter(hasValidPosition).length
  const visibleOnMap = filtered.filter(hasValidPosition).length
  const attentionCount = events.filter((event) => needsAttention(event, now)).length
  const allStale = events.length > 0 && events.every((event) => isStale(event, now))

  return (
    <div className={`dispatch-screen${detailsOpen ? '' : ' dispatch-screen--details-collapsed'}`} style={{ '--sidebar-width': `${sidebarWidth}px` } as CSSProperties}>
      <aside aria-label="Список терминалов" className="dispatch-sidebar">
        <div className="dispatch-sidebar__toolbar">
          <div className="dispatch-sidebar__heading"><h1>Терминалы</h1><span>{isPending || isError ? '—' : events.length}</span></div>
          <label className="fleet-search"><Search aria-hidden size={18} /><input aria-label="Поиск по ID терминала" inputMode="numeric" onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по ID терминала" value={query} /></label>
          <label className="fleet-filter"><span className="sr-only">Фильтр по состоянию</span><select onChange={(e) => setFilter(e.target.value as FleetFilter)} value={filter}>{filterOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        </div>
        <div className="fleet-list" role="list">
          {isPending ? <p className="fleet-list__message">Загружаем транспорт…</p> : isError && events.length === 0 ? <p className="fleet-list__message">Нет связи с сервером.</p> : events.length === 0 ? <p className="fleet-list__message">Данные транспорта пока не поступали.</p> : filtered.length === 0 ? <p className="fleet-list__message">По выбранному поиску и фильтру терминалов нет.</p> : (
            <>
              {attention.length > 0 && <div className="fleet-list__group"><AlertTriangle size={14} /><span>Требуют внимания</span><b>{attention.length}</b></div>}
              {attention.map((event) => <FleetRow event={event} key={event.unit_id} onSelect={() => selectUnit(event.unit_id)} selected={event.unit_id === selectedUnitId} />)}
              {rest.length > 0 && <div className="fleet-list__group fleet-list__group--neutral"><span>Остальные терминалы</span><b>{rest.length}</b></div>}
              {rest.map((event) => <FleetRow event={event} key={event.unit_id} onSelect={() => selectUnit(event.unit_id)} selected={event.unit_id === selectedUnitId} />)}
            </>
          )}
        </div>
      </aside>

      <div aria-label="Изменить ширину списка терминалов" aria-valuemax={620} aria-valuemin={280} aria-valuenow={sidebarWidth} className="sidebar-resizer" onDoubleClick={() => setSidebarWidth(sidebarWidth === 280 ? 620 : 280)} onPointerDown={resizeSidebar} role="separator" title="Перетащите, чтобы изменить ширину списка. Двойной щелчок — минимум/максимум." />

      <main className="dispatch-map-area">
        <div className="dispatch-map-area__meta">
          <div className="fleet-stats"><span><strong>{isPending || isError ? '—' : events.length}</strong> терминалов</span><span><strong>{isPending || isError ? '—' : onMap}</strong> на карте</span><span><strong>{isPending || isError ? '—' : attentionCount}</strong> требуют внимания</span></div>
          <div className="poll-status">{streamConnected || dataUpdatedAt ? 'Связь активна' : 'Ожидаем соединение'}</div>
        </div>
        <div className="dispatch-map-area__map">
          <VehicleMap events={filtered} predictions={predictions} onSelect={selectUnit} selectedHistory={selectedHistory} selectedUnitId={selectedUnitId} />
          {isPending && <div className="map-state"><strong>Загружаем позиции</strong></div>}
          {isError && !isPending && <div className="map-state map-state--error"><WifiOff size={20} /><strong>Нет связи с сервером</strong><span>Данные временно недоступны.</span></div>}
          {!isPending && !isError && events.length === 0 && <div className="map-state"><strong>Нет транспорта на карте</strong><span>Ожидаем новые данные.</span></div>}
          {!isPending && !isError && events.length > 0 && filtered.length === 0 && <div className="map-state"><strong>Нет совпадений</strong><span>Измените поиск или фильтр состояния.</span></div>}
          {!isPending && !isError && filtered.length > 0 && visibleOnMap === 0 && <div className="map-state"><MapPinOff size={20} /><strong>Нет валидных координат</strong><span>Выбранные терминалы видны в списке слева.</span></div>}
          {allStale && !isError && <div className="map-warning"><Clock3 size={16} /> Все последние координаты устарели</div>}
          <div className="map-legend"><span><Navigation2 size={14} /> Движется</span><span><Square size={13} /> Стоит</span><span><Clock3 size={14} /> Устарели</span><span className="map-legend__track">— GPS-след</span><span><AlertTriangle size={14} /> Тревога</span></div>
        </div>
      </main>

      <aside className="details-panel">
        <button aria-expanded={detailsOpen} className="details-panel__toggle" onClick={() => setDetailsOpen(!detailsOpen)} title={detailsOpen ? 'Свернуть статистику' : 'Развернуть статистику'} type="button">
          {detailsOpen ? <ChevronRight size={21} strokeWidth={2.5} /> : <ChevronLeft size={21} strokeWidth={2.5} />}
          <span className="sr-only">{detailsOpen ? 'Свернуть статистику' : 'Развернуть статистику'}</span>
        </button>
        {detailsOpen && <VehicleDetails event={selectedEvent} prediction={selectedPrediction} />}
      </aside>
    </div>
  )
}

export function DashboardPage() {
  const source = useDashboardStore((state) => state.source)
  return source === 'historical' ? <HistoricalFleetDashboard /> : <LiveDashboard />
}
