import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'

import { VehiclesTable } from '@/features/vehicles/VehiclesTable'
import { usePredictions } from '@/features/predictions/api'
import { useVehicleFeed } from '@/features/vehicles/hooks'
import { useTelemetryStore } from '@/store/telemetry'
import { useDashboardStore } from '@/store/dashboard'
import { HistoricalVehiclesTable } from '@/features/replay/HistoricalVehiclesTable'
import { VehicleDetails } from './DashboardPage'

export function VehiclesPage() {
  const source = useDashboardStore((state) => state.source)
  return source === 'historical' ? <HistoricalVehiclesTable /> : <NdtpVehiclesTable />
}

function NdtpVehiclesTable() {
  const { data: events = [] } = useVehicleFeed()
  const { data: predictions = [] } = usePredictions()
  const selectedUnitId = useTelemetryStore((state) => state.selectedUnitId)
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const needle = query.trim()
    if (!needle) return events
    return events.filter((event) => String(event.unit_id).includes(needle))
  }, [events, query])

  const selectedEvent =
    events.find((event) => event.unit_id === selectedUnitId) ?? filtered[0]
  const selectedPrediction = predictions.find((prediction) => prediction.unit_id === selectedEvent?.unit_id)

  return (
    <div className="page">
      <div className="grid-2">
        <section className="panel">
          <header className="panel__head">
            <h2>Терминалы</h2>
            <label className="search">
              <Search size={14} />
              <input
                inputMode="numeric"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="поиск по ID"
                value={query}
              />
            </label>
          </header>
          <VehiclesTable events={filtered} predictions={predictions} />
        </section>

        <section className="panel">
          <header className="panel__head">
            <h2>Выбранный транспорт</h2>
          </header>
          <VehicleDetails event={selectedEvent} prediction={selectedPrediction} />
        </section>
      </div>
    </div>
  )
}
