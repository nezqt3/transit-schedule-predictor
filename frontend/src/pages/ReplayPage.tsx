import { useEffect, useMemo, useRef, useState } from 'react'

import { predictReplayPoint, useReplayScenario, useReplayVehicles } from '@/features/replay/api'
import { ReplayMap } from '@/features/replay/ReplayMap'
import type { ReplayPrediction } from '@/types/replay'

const clock = (value: string | number) => new Date(value).toLocaleTimeString('ru-RU', {
  hour: '2-digit', minute: '2-digit', second: '2-digit',
})
const seconds = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(0)} с`

export function ReplayPage() {
  const { data: vehicles = [], isError: vehiclesError } = useReplayVehicles()
  const [trId, setTrId] = useState<number | null>(null)
  useEffect(() => {
    if (trId === null && vehicles.length > 0) setTrId(vehicles[0]!.tr_id)
  }, [vehicles, trId])
  const { data: scenario, isPending, isError } = useReplayScenario(trId)
  const [timeMs, setTimeMs] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(600)
  const [predictions, setPredictions] = useState<Record<string, ReplayPrediction>>({})
  const [failures, setFailures] = useState<Record<string, string>>({})
  const requested = useRef(new Set<string>())

  useEffect(() => {
    if (!scenario) return
    setTimeMs(Date.parse(scenario.vehicle.start_at))
    setPlaying(false)
    setPredictions({})
    setFailures({})
    requested.current.clear()
  }, [scenario?.vehicle.tr_id])

  const startMs = scenario ? Date.parse(scenario.vehicle.start_at) : 0
  const endMs = scenario ? Date.parse(scenario.vehicle.end_at) : 0
  useEffect(() => {
    if (!playing || !scenario) return
    const timer = window.setInterval(() => {
      setTimeMs((current) => Math.min(current + 200 * speed, endMs))
    }, 200)
    return () => window.clearInterval(timer)
  }, [playing, speed, endMs, scenario])
  useEffect(() => {
    if (playing && timeMs >= endMs && endMs > 0) setPlaying(false)
  }, [playing, timeMs, endMs])

  useEffect(() => {
    if (!scenario || timeMs < startMs) return
    const next = scenario.points.find((point) =>
      Date.parse(point.T) <= timeMs && !requested.current.has(point.sample_id))
    if (!next) return
    requested.current.add(next.sample_id)
    predictReplayPoint(next.sample_id)
      .then((result) => setPredictions((current) => ({ ...current, [next.sample_id]: result })))
      .catch((error: Error) => setFailures((current) => ({ ...current, [next.sample_id]: error.message })))
  }, [scenario, timeMs, startMs, predictions, failures])

  const matured = useMemo(() => scenario?.points.filter((point) =>
    Date.parse(point.actual_at) <= timeMs && predictions[point.sample_id]) ?? [],
  [scenario, timeMs, predictions])
  const mae = (baseline: boolean) => matured.length
    ? matured.reduce((sum, point) => sum + Math.abs(
      (baseline ? point.cur_dev_s : predictions[point.sample_id]!.predicted_delay_s)
      - point.actual_delay_s,
    ), 0) / matured.length : null
  const latest = scenario?.points.filter((point) => Date.parse(point.T) <= timeMs).at(-1)
  const completed = scenario ? timeMs >= endMs : false

  const nextPoint = () => {
    if (!scenario) return
    const next = scenario.points.find((point) => Date.parse(point.T) > timeMs)
    setPlaying(false)
    setTimeMs(next ? Date.parse(next.T) : endMs)
  }
  const restart = () => {
    setPlaying(false)
    setTimeMs(startMs)
  }

  return (
    <div className="replay-page">
      <header className="replay-head">
        <div>
          <span className="eyebrow">Отдельный источник · CSV января 2026</span>
          <h1>Исторический прогон</h1>
          <p>Реальные записанные GPS и плановые остановки. Модель получает только данные, доступные к моменту T; на экране факт появляется после прибытия.</p>
        </div>
        <div className="replay-source">Локальный test · те же сутки, что train<br />Проверка работы и ошибок по остановкам</div>
      </header>

      <section className="replay-controls" aria-label="Управление воспроизведением">
        <label>Транспорт
          <select disabled={vehicles.length === 0} onChange={(event) => setTrId(Number(event.target.value))} value={trId ?? ''}>
            {vehicles.map((vehicle) => <option key={vehicle.tr_id} value={vehicle.tr_id}>ТС {vehicle.tr_id} · терминал {vehicle.unit_id} · {vehicle.samples} прогнозов</option>)}
          </select>
        </label>
        <div className="replay-buttons">
          <button disabled={!scenario || completed} onClick={() => setPlaying(!playing)} type="button">{playing ? 'Пауза' : '▶ Пуск'}</button>
          <button disabled={!scenario} onClick={nextPoint} type="button">Следующий прогноз</button>
          <button disabled={!scenario} onClick={() => { setPlaying(false); setTimeMs(endMs) }} type="button">Прогнать всё</button>
          <button disabled={!scenario} onClick={restart} type="button">С начала</button>
        </div>
        <label>Скорость
          <select onChange={(event) => setSpeed(Number(event.target.value))} value={speed}>
            <option value={60}>60×</option><option value={300}>300×</option>
            <option value={600}>600×</option><option value={1800}>1800×</option>
          </select>
        </label>
      </section>

      {vehiclesError && <p className="replay-message">Исторические CSV недоступны в backend.</p>}
      {isError && <p className="replay-message">Не удалось загрузить исторический сценарий.</p>}
      {isPending && trId !== null && <p className="replay-message">Загружаем записанный маршрут…</p>}
      {scenario && <>
        <section className="replay-timeline">
          <strong>{clock(timeMs)}</strong>
          <input aria-label="Момент исторической записи" max={endMs} min={startMs} onChange={(event) => { setPlaying(false); setTimeMs(Number(event.target.value)) }} step={1000} type="range" value={Math.min(Math.max(timeMs, startMs), endMs)} />
          <span>{clock(endMs)}</span>
          <small>6 января 2026 · GPS отображается по времени поступления</small>
        </section>
        <div className="replay-metrics">
          <div><span>Прогнозов</span><strong>{Object.keys(predictions).length} / {scenario.points.length}</strong></div>
          <div><span>Факт уже известен</span><strong>{matured.length}</strong></div>
          <div><span>MAE модели</span><strong>{mae(false)?.toFixed(1) ?? '—'} <small>{matured.length ? 'с' : ''}</small></strong></div>
          <div><span>MAE baseline cur_dev</span><strong>{mae(true)?.toFixed(1) ?? '—'} <small>{matured.length ? 'с' : ''}</small></strong></div>
        </div>
        <div className="replay-main">
          <div className="replay-map-wrap"><ReplayMap scenario={scenario} timeMs={timeMs} /><div className="replay-map-legend"><span>● GPS к выбранному времени</span><span>● Плановые остановки</span><span>● Целевые остановки</span></div></div>
          <section className="replay-current">
            <span className="eyebrow">Текущий прогноз</span>
            {latest ? <>
              <h2>Остановка {latest.target_stop_id}</h2>
              <p>Расписание {clock(latest.target_time_begin)} · прогноз от {clock(latest.T)}</p>
              <div><span>Текущее отклонение</span><strong>{seconds(latest.cur_dev_s)}</strong></div>
              <div><span>Прогноз модели</span><strong>{predictions[latest.sample_id] ? seconds(predictions[latest.sample_id]!.predicted_delay_s) : failures[latest.sample_id] ? 'Ошибка ML' : 'Рассчитываем…'}</strong></div>
              <div><span>Факт на остановке</span><strong>{Date.parse(latest.actual_at) <= timeMs && predictions[latest.sample_id] ? seconds(latest.actual_delay_s) : 'Пока неизвестен'}</strong></div>
              {failures[latest.sample_id] && <button onClick={() => { requested.current.delete(latest.sample_id); setFailures((current) => { const next = { ...current }; delete next[latest.sample_id]; return next }) }} type="button">Повторить прогноз</button>}
            </> : <p>Перед первой точкой прогноза. Запустите запись или перейдите к следующей точке.</p>}
          </section>
        </div>
        <section className="replay-results">
          <div className="replay-results__head"><h2>Проверка по целевым остановкам</h2><span>{scenario.points.length} точек с известным фактом</span></div>
          <div className="replay-results__scroll"><table>
            <thead><tr><th>Прогноз T</th><th>Остановка</th><th>План</th><th>Сейчас</th><th>Прогноз</th><th>Факт</th><th>Ошибка</th></tr></thead>
            <tbody>{scenario.points.map((point) => {
              const prediction = Date.parse(point.T) <= timeMs ? predictions[point.sample_id] : undefined
              const known = prediction && Date.parse(point.actual_at) <= timeMs
              const error = known ? Math.abs(prediction.predicted_delay_s - point.actual_delay_s) : null
              return <tr className={latest?.sample_id === point.sample_id ? 'replay-results__active' : ''} key={point.sample_id}>
                <td>{clock(point.T)}</td><td>#{point.target_stop_id}</td><td>{clock(point.target_time_begin)}</td>
                <td>{Date.parse(point.T) <= timeMs ? seconds(point.cur_dev_s) : '—'}</td>
                <td>{prediction ? seconds(prediction.predicted_delay_s) : failures[point.sample_id] ? 'Ошибка' : Date.parse(point.T) <= timeMs ? '…' : '—'}</td>
                <td>{known ? seconds(point.actual_delay_s) : '—'}</td><td>{error === null ? '—' : `${error.toFixed(1)} с`}</td>
              </tr>
            })}</tbody>
          </table></div>
        </section>
      </>}
    </div>
  )
}
