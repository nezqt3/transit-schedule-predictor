import { Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { statusLabel } from '@/lib/telemetry/vehicleStatus'
import { useDashboardStore } from '@/store/dashboard'
import { useReplayFleet } from './api'
import { displaySpeedKmh, fleetSnapshot, janClock, janMs, stopLabel } from './fleetClock'
import { HistoricalVehicleDetails } from './HistoricalVehicleDetails'

const signed = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(0)} с`

export function HistoricalVehiclesTable() {
  const { data: fleet, isPending, isError } = useReplayFleet()
  const timeMs = useDashboardStore((state) => state.replayTimeMs)
  const predictions = useDashboardStore((state) => state.replayPredictions)
  const failures = useDashboardStore((state) => state.replayFailures)
  const selectedId = useDashboardStore((state) => state.selectedReplayId)
  const selectVehicle = useDashboardStore((state) => state.selectReplayVehicle)
  const [query, setQuery] = useState('')
  const rows = useMemo(() => fleetSnapshot(fleet, timeMs, predictions), [fleet, timeMs, predictions])
  const filtered = rows.filter((item) => String(item.vehicle.tr_id).includes(query.trim())
    || String(item.vehicle.unit_id).includes(query.trim()))
  const selected = fleet?.vehicles.find((vehicle) => vehicle.tr_id === selectedId) ?? null

  useEffect(() => {
    if (!rows.length && selectedId !== null) { selectVehicle(null); return }
    if (rows.length && !rows.some((item) => item.vehicle.tr_id === selectedId)) {
      selectVehicle(rows[0]!.vehicle.tr_id)
    }
  }, [selectedId, rows, selectVehicle])

  return <div className="page">
    <div className="grid-2 historical-table-layout">
      <section className="panel">
        <header className="panel__head"><h1>Транспорт на линии <span className="historical-table-count">{rows.length}</span></h1><label className="search"><Search size={15} /><input aria-label="Поиск транспорта" inputMode="numeric" onChange={(event) => setQuery(event.target.value)} placeholder="Поиск ТС или терминала" value={query} /></label></header>
        <div className="historical-table-scroll"><table className="table historical-vehicles-table">
          <thead><tr><th>Транспорт</th><th>Состояние</th><th>Рейс</th><th>Скорость</th><th>Прогноз 10–15 мин</th><th>Текущее отклонение</th><th>Целевая остановка</th></tr></thead>
          <tbody>
            {filtered.map(({ vehicle, gps, status, run, point, forecast, late }) => {
              const speed = displaySpeedKmh(gps?.speed ?? null)
              return <tr aria-current={vehicle.tr_id === selectedId ? 'true' : undefined} className={vehicle.tr_id === selectedId ? 'table__row--selected' : undefined} key={vehicle.tr_id} onClick={() => selectVehicle(vehicle.tr_id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectVehicle(vehicle.tr_id) } }} tabIndex={0}>
                <td><strong>ТС {vehicle.tr_id}</strong><small>Терминал {vehicle.unit_id}</small></td>
                <td><span className={`historical-state historical-state--${status}`}>{statusLabel[status]}</span></td>
                <td>{run ? run.run_id : '—'}</td>
                <td>{speed === null ? '—' : `${speed.toFixed(0)} км/ч`}</td>
                <td className={late ? 'historical-late' : undefined}><strong>{point ? forecast ? signed(forecast.predicted_delay_s) : failures[point.sample_id] ? 'Недоступен' : 'Рассчитываем…' : '—'}</strong></td>
                <td>{point ? signed(point.cur_dev_s) : '—'}</td>
                <td>{point ? <>{stopLabel(vehicle, point.target_stop_id)}<small>{forecast ? `Ожидаем ${janClock(janMs(point.target_time_begin) + forecast.predicted_delay_s * 1000)}` : `План ${janClock(point.target_time_begin)}`}</small></> : '—'}</td>
              </tr>
            })}
            {!filtered.length && <tr><td className="table__empty" colSpan={7}>{isPending ? 'Подключаем транспорт…' : isError ? 'Не удалось получить данные транспорта.' : rows.length ? 'Поиск не дал результатов.' : 'Ожидаем транспорт на линии.'}</td></tr>}
          </tbody>
        </table></div>
      </section>
      <section className="panel historical-table-details"><HistoricalVehicleDetails vehicle={selected} timeMs={timeMs} /></section>
    </div>
  </div>
}
