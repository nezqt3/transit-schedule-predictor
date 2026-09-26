import { AlertTriangle, ArrowRight, BusFront, ChevronLeft, ChevronRight, Clock3, MapPinOff, Navigation2, Search, Square, WifiOff } from 'lucide-react'
import { useEffect, useMemo, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'

import { useVehicleHistory } from '@/features/vehicles/api'
import { useIncidents, usePredictionStatuses, usePredictions } from '@/features/predictions/api'
import { VehicleMap } from '@/features/vehicles/VehicleMap'
import { fleetStatusIcons } from '@/features/vehicles/markerIcon'
import { useVehicleFeed } from '@/features/vehicles/hooks'
import { formatAge, formatClock, formatDateTime } from '@/lib/format/time'
import { eventTimeMs, hasValidPosition, isStale, speedKmh } from '@/lib/telemetry/readEvent'
import { hasAlarm, needsAttention, statusLabel, vehicleStatus, type VehicleStatus } from '@/lib/telemetry/vehicleStatus'
import { useTelemetryStore } from '@/store/telemetry'
import { HistoricalFleetDashboard } from '@/features/replay/HistoricalFleetDashboard'
import { WhatIfPanel } from '@/features/what-if/WhatIfPanel'
import { useDashboardStore } from '@/store/dashboard'
import type { Incident, PredictionStatus, StoredPrediction, TelemetryEvent } from '@/types/api'

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

function forecastRisk(prediction: StoredPrediction | undefined) {
  return prediction?.freshness === 'stale' ? undefined : prediction?.risk
}

function needsDispatcherAttention(event: TelemetryEvent, prediction: StoredPrediction | undefined, now: number) {
  return forecastRisk(prediction) === 'high' || forecastRisk(prediction) === 'medium'
    || needsAttention(event, now)
}

function matchesFilter(event: TelemetryEvent, prediction: StoredPrediction | undefined,
  filter: FleetFilter, now: number) {
  if (filter === 'all') return true
  if (filter === 'attention') return needsDispatcherAttention(event, prediction, now)
  if (filter === 'alarm') return hasAlarm(event)
  if (filter === 'stale') return isStale(event, now)
  if (filter === 'no-position') return !hasValidPosition(event)
  return vehicleStatus(event, now) === filter
}

function FleetRow({ event, prediction, selected, onSelect }: {
  event: TelemetryEvent
  prediction: StoredPrediction | undefined
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
      {forecastRisk(prediction) && <span className={`forecast-risk forecast-risk--${forecastRisk(prediction)}`}>{forecastRisk(prediction) === 'high' ? 'Высокий риск' : forecastRisk(prediction) === 'medium' ? 'Риск' : 'Норма'}</span>}
      {speed !== null && <span className="fleet-row__speed">{speed.toFixed(0)} <small>км/ч</small></span>}
      <ArrowRight aria-hidden size={16} className="fleet-row__arrow" />
    </button>
  )
}

const statusText: Record<string, string> = {
  schedule_unmatched: 'Нет связи терминала с расписанием',
  no_target_in_horizon: 'Нет остановки через 10–15 минут',
  insufficient_data: 'Недостаточно данных для текущего отклонения',
  invalid_telemetry: 'Нет достоверной GPS-точки',
  ml_unavailable: 'Сервис прогноза временно недоступен',
  invalid_prediction: 'Ошибка расчёта прогноза',
}

export function VehicleDetails({ event, prediction, incident, predictionStatus }: {
  event: TelemetryEvent | undefined
  prediction: StoredPrediction | undefined
  incident?: Incident
  predictionStatus?: PredictionStatus
}) {
  if (!event) {
    return <div className="vehicle-details vehicle-details--empty"><strong>Выберите терминал</strong><span>Данные появятся здесь после выбора в списке или на карте.</span></div>
  }

  const status = vehicleStatus(event)
  const speed = speedKmh(event)
  const risk = forecastRisk(prediction)
  return (
    <section aria-label={`Данные терминала ${event.unit_id}`} className="vehicle-details">
      <div className="vehicle-details__top">
        <div><span className="eyebrow">Выбранный терминал</span><h2>#{event.unit_id}</h2></div>
        <span className={`state-pill state-pill--${status}`}>{statusLabel[status]}</span>
      </div>
      <div className="historical-priority">
        <div className={`historical-priority__forecast${risk === 'high' ? ' historical-priority__forecast--late' : ''}`}>
          <span>Прогноз через 10–15 мин · {prediction?.source === 'demo' ? 'синтетический план эмулятора' : prediction?.source === 'replay' ? 'исторический NDTP' : prediction?.source === 'manual' ? 'ручной расчёт' : 'живой NDTP'}</span>
          <strong>{prediction ? `${prediction.predicted_delay_s > 0 ? '+' : ''}${prediction.predicted_delay_s.toFixed(0)} с` : 'Нет прогноза'}</strong>
          <small>{prediction ? `План ${formatClock(prediction.target_time)} МСК · ожидаем ${formatClock(prediction.predicted_arrival ?? Date.parse(prediction.target_time) + prediction.predicted_delay_s * 1000)} МСК` : statusText[predictionStatus?.code ?? ''] ?? 'Ожидаем расписание и телеметрию'}</small>
        </div>
      </div>
      {prediction && <div className="vehicle-details__facts">
        <div><span>Риск опоздания</span><strong className={`risk-text risk-text--${risk ?? 'low'}`}>{prediction.freshness === 'stale' ? 'Прогноз устарел' : risk === 'high' ? 'Высокий' : risk === 'medium' ? 'Средний' : 'Низкий'}</strong></div>
        <div><span>Вероятность ≥120 с</span><strong>{prediction.p_late == null ? 'Не рассчитана' : `${(prediction.p_late * 100).toFixed(0)} %`}</strong></div>
        <div><span>Текущее отклонение</span><strong>{prediction.current_delay_s.toFixed(0)} с · {prediction.current_delay_source === 'demo_anchor' ? 'демо-допущение' : prediction.current_delay_source === 'point_input' ? 'входная точка' : 'остановка'}</strong></div>
        <div><span>Время прогноза</span><strong>{formatClock(prediction.produced_at ?? prediction.prediction_time)} МСК</strong></div>
      </div>}
      {incident && <div className={`incident-card incident-card--${incident.risk}`}>
        <strong>{incident.risk === 'high' ? 'Высокий риск' : 'Средний риск'} · участок {incident.segment}</strong>
        <small>Рейс #{incident.tr_id} · терминал #{incident.unit_id} · остановка #{incident.target_stop_id}</small>
        <small>План {formatDateTime(incident.target_time)} МСК · ожидаем {formatDateTime(Date.parse(incident.target_time) + incident.predicted_delay_s * 1000)} МСК</small>
        <small>Отклонение {incident.predicted_delay_s.toFixed(0)} с ({(incident.predicted_delay_s / 60).toFixed(1)} мин){incident.p_late == null ? '' : ` · вероятность ≥120 с: ${(incident.p_late * 100).toFixed(0)} %`}</small>
        <span>{incident.cause}</span>
        <small>{incident.evidence}</small>
        <p>{incident.recommendation}</p>
      </div>}
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
  const { data: incidents = [] } = useIncidents()
  const { data: predictionStatuses = [] } = usePredictionStatuses()
  const selectedUnitId = useTelemetryStore((state) => state.selectedUnitId)
  const selectUnit = useTelemetryStore((state) => state.selectUnit)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FleetFilter>('all')
  const [sidebarWidth, setSidebarWidth] = useState(390)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [whatIfOpen, setWhatIfOpen] = useState(false)
  const now = Date.now()
  const byUnit = useMemo(() => new Map(predictions.map((prediction) => [prediction.unit_id, prediction])), [predictions])

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
    return matchesSearch && matchesFilter(event, byUnit.get(event.unit_id), filter, now)
  }), [events, byUnit, filter, query, now])

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
  const selectedIncident = incidents.find((incident) => incident.unit_id === selectedUnitId && incident.status === 'active')
  const selectedPredictionStatus = predictionStatuses.find((item) => item.unit_id === selectedUnitId)
  const attention = filtered.filter((event) => needsDispatcherAttention(event, byUnit.get(event.unit_id), now))
  const rest = filtered.filter((event) => !needsDispatcherAttention(event, byUnit.get(event.unit_id), now))
  const onMap = events.filter(hasValidPosition).length
  const visibleOnMap = filtered.filter(hasValidPosition).length
  const attentionCount = events.filter((event) => needsDispatcherAttention(event, byUnit.get(event.unit_id), now)).length
  const allStale = events.length > 0 && events.every((event) => isStale(event, now))
  const historicalNdtp = events.some((event) => event.nav &&
    Math.abs(Date.parse(event.received_at) - event.nav.timestamp * 1000) > 24 * 60 * 60 * 1000)
  const activeUnitIds = new Set(events.map((event) => event.unit_id))
  const whatIfVehicles = predictions.filter((prediction) =>
    activeUnitIds.has(prediction.unit_id)).map((prediction) => ({
    tr_id: prediction.tr_id,
    predicted_delay_s: prediction.predicted_delay_s,
    target_stop_id: prediction.target_stop_id,
  }))

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
              {attention.map((event) => <FleetRow event={event} prediction={byUnit.get(event.unit_id)} key={event.unit_id} onSelect={() => selectUnit(event.unit_id)} selected={event.unit_id === selectedUnitId} />)}
              {rest.length > 0 && <div className="fleet-list__group fleet-list__group--neutral"><span>Остальные терминалы</span><b>{rest.length}</b></div>}
              {rest.map((event) => <FleetRow event={event} prediction={byUnit.get(event.unit_id)} key={event.unit_id} onSelect={() => selectUnit(event.unit_id)} selected={event.unit_id === selectedUnitId} />)}
            </>
          )}
        </div>
      </aside>

      <div aria-label="Изменить ширину списка терминалов" aria-valuemax={620} aria-valuemin={280} aria-valuenow={sidebarWidth} className="sidebar-resizer" onDoubleClick={() => setSidebarWidth(sidebarWidth === 280 ? 620 : 280)} onPointerDown={resizeSidebar} role="separator" title="Перетащите, чтобы изменить ширину списка. Двойной щелчок — минимум/максимум." />

      <main className="dispatch-map-area">
        <div className="dispatch-map-area__meta">
          <div className="fleet-stats"><span><strong>{isPending || isError ? '—' : events.length}</strong> терминалов</span><span><strong>{isPending || isError ? '—' : onMap}</strong> на карте</span><span><strong>{isPending || isError ? '—' : attentionCount}</strong> требуют внимания</span></div>
          <div className="dispatch-map-area__actions"><button aria-pressed={whatIfOpen} onClick={() => setWhatIfOpen(!whatIfOpen)} type="button"><BusFront size={15} /> What-if</button><div className="poll-status">{historicalNdtp ? 'Исторический NDTP · архив' : 'Живой NDTP'} · {streamConnected ? 'связь активна' : dataUpdatedAt ? 'ожидаем поток' : 'нет соединения'}</div></div>
        </div>
        <div className="dispatch-map-area__map">
          <VehicleMap events={filtered} predictions={predictions} onSelect={selectUnit} selectedHistory={selectedHistory} selectedUnitId={selectedUnitId} />
          {whatIfOpen && <WhatIfPanel context="Текущий NDTP-поток" onClose={() => setWhatIfOpen(false)} vehicles={whatIfVehicles} />}
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
        {detailsOpen && <VehicleDetails event={selectedEvent} prediction={selectedPrediction} incident={selectedIncident} predictionStatus={selectedPredictionStatus} />}
      </aside>
    </div>
  )
}

export function DashboardPage() {
  const source = useDashboardStore((state) => state.source)
  return source === 'historical' ? <HistoricalFleetDashboard /> : <LiveDashboard />
}
