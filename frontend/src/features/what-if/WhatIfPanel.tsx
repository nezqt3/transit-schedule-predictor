import { ArrowDown, BusFront, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { analyzeWhatIf } from './api'
import type { WhatIfResponse, WhatIfVehicle } from '@/types/api'

type WhatIfPanelProps = {
  context: string
  vehicles: WhatIfVehicle[]
  onClose: () => void
}

const seconds = (value: number) => `${Math.round(value)} с`

export function WhatIfPanel({ context, vehicles, onClose }: WhatIfPanelProps) {
  const [additionalVehicles, setAdditionalVehicles] = useState(1)
  const [dispatchLeadMinutes, setDispatchLeadMinutes] = useState(3)
  const [passengerCount, setPassengerCount] = useState(60)
  const [trafficMultiplier, setTrafficMultiplier] = useState(1.2)
  const [reserveCapacity, setReserveCapacity] = useState(100)
  const [turnaroundMinutes, setTurnaroundMinutes] = useState(10)
  const [result, setResult] = useState<WhatIfResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const scenarioKey = vehicles.map((vehicle) =>
    `${vehicle.tr_id}:${vehicle.predicted_delay_s}:${vehicle.run_id ?? ''}`).join('|')
  const currentScenarioKey = useRef(scenarioKey)

  useEffect(() => {
    currentScenarioKey.current = scenarioKey
    setResult(null)
    setError(null)
  }, [context, scenarioKey])

  const calculate = async () => {
    if (!vehicles.length) return
    setPending(true)
    setError(null)
    const requestedScenarioKey = scenarioKey
    try {
      const response = await analyzeWhatIf({
        vehicles: vehicles.map((vehicle) => ({
          ...vehicle,
          passenger_count: vehicle.passenger_count ?? passengerCount,
          vehicle_capacity: vehicle.vehicle_capacity ?? 100,
          remaining_trip_minutes: vehicle.remaining_trip_minutes ?? 25,
          next_run_departure_minutes: vehicle.next_run_departure_minutes ?? 35,
          turnaround_minutes: vehicle.turnaround_minutes ?? turnaroundMinutes,
          rotation_runs: vehicle.rotation_runs ?? [
            { run_id: `${vehicle.run_id ?? vehicle.tr_id}-next-1`, departure_minutes: 35, duration_minutes: 30 },
            { run_id: `${vehicle.run_id ?? vehicle.tr_id}-next-2`, departure_minutes: 80, duration_minutes: 30 },
          ],
        })),
        additional_vehicles: additionalVehicles,
        dispatch_lead_minutes: dispatchLeadMinutes,
        late_threshold_s: 120,
        traffic_multiplier: trafficMultiplier,
        reserve_capacity: reserveCapacity,
        passenger_transfer_minutes: 2,
      })
      if (currentScenarioKey.current === requestedScenarioKey) setResult(response)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось рассчитать сценарий')
    } finally {
      setPending(false)
    }
  }

  return <section aria-label="What-if анализ" className="what-if-panel">
    <div className="what-if-panel__head">
      <div><span className="eyebrow">Сценарное моделирование</span><h2>Выпустить резервное ТС</h2></div>
      <button aria-label="Закрыть what-if анализ" onClick={onClose} type="button"><X size={18} /></button>
    </div>
    <p className="what-if-panel__context">{context} · {vehicles.length} активных прогнозов</p>
    <div className="what-if-panel__controls">
      <label><span>Дополнительных ТС</span><input max={10} min={1} onChange={(event) => { setAdditionalVehicles(Math.min(10, Math.max(1, Number(event.target.value) || 1))); setResult(null) }} type="number" value={additionalVehicles} /></label>
      <label><span>Выход на линию</span><select onChange={(event) => { setDispatchLeadMinutes(Number(event.target.value)); setResult(null) }} value={dispatchLeadMinutes}><option value={0}>сразу</option><option value={3}>через 3 мин</option><option value={5}>через 5 мин</option><option value={10}>через 10 мин</option><option value={15}>через 15 мин</option></select></label>
      <label><span>Пассажиров на рейсе</span><input max={500} min={0} onChange={(event) => { setPassengerCount(Math.max(0, Number(event.target.value) || 0)); setResult(null) }} type="number" value={passengerCount} /></label>
      <label><span>Загрузка дорог</span><select onChange={(event) => { setTrafficMultiplier(Number(event.target.value)); setResult(null) }} value={trafficMultiplier}><option value={1}>обычная</option><option value={1.2}>+20%</option><option value={1.5}>+50%</option><option value={2}>x2</option></select></label>
      <label><span>Вместимость резерва</span><input max={500} min={1} onChange={(event) => { setReserveCapacity(Math.max(1, Number(event.target.value) || 1)); setResult(null) }} type="number" value={reserveCapacity} /></label>
      <label><span>Оборот между рейсами</span><input max={180} min={0} onChange={(event) => { setTurnaroundMinutes(Math.max(0, Number(event.target.value) || 0)); setResult(null) }} type="number" value={turnaroundMinutes} /></label>
    </div>
    <button className="what-if-panel__run" disabled={pending || !vehicles.length} onClick={calculate} type="button"><BusFront size={17} /> {pending ? 'Рассчитываем…' : 'Оценить влияние'}</button>
    {!vehicles.length && <p className="what-if-panel__empty">Сначала дождитесь прогнозов по активным рейсам.</p>}
    {error && <p className="what-if-panel__error">{error}</p>}
    {result && <>
      <div className="what-if-comparison">
        <div><span>Сейчас</span><strong>{result.baseline.late_runs}</strong><small>рейсов ≥ 2 мин</small></div>
        <ArrowDown aria-hidden size={20} />
        <div className="what-if-comparison__after"><span>С резервом</span><strong>{result.scenario.late_runs}</strong><small>рейсов ≥ 2 мин</small></div>
      </div>
      <div className="what-if-metrics">
        <div><span>Средняя задержка</span><strong>{seconds(result.baseline.average_delay_s)} → {seconds(result.scenario.average_delay_s)}</strong></div>
        <div><span>Максимальная</span><strong>{seconds(result.baseline.maximum_delay_s)} → {seconds(result.scenario.maximum_delay_s)}</strong></div>
        <div><span>Суммарно сэкономлено</span><strong>{seconds(result.total_delay_reduction_s)}</strong></div>
        <div><span>Пассажиро-минут сэкономлено</span><strong>{Math.round(result.total_passenger_delay_reduction_minutes)}</strong></div>
        <div><span>Задержка следующих рейсов</span><strong>{seconds(result.baseline.rotation_delay_s)} → {seconds(result.scenario.rotation_delay_s)}</strong></div>
      </div>
      {result.assignments.length > 0 ? <div className="what-if-assignments"><strong>Рекомендуемые назначения</strong>{result.assignments.map((item) => <div key={item.reserve_vehicle}><span>Резерв {item.reserve_vehicle} → ТС {item.tr_id}{item.run_id ? ` · рейс ${item.run_id}` : ''} · {item.served_passengers}/{item.passenger_count} пасс.</span><b>−{seconds(item.reduction_s)}</b></div>)}</div> : <p className="what-if-panel__empty">При выбранном времени выхода резерв не успевает улучшить текущий прогноз.</p>}
      <p className="what-if-panel__assumption">Оценка, не команда диспетчеризации. Учтены загрузка дорог, пассажиропоток и вместимость резерва, время пересадки, остаток рейса и оборот ТС перед следующим рейсом.</p>
    </>}
  </section>
}
