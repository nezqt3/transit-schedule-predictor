import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'

import { VehicleFocus } from '@/features/vehicles/VehicleFocus'
import { VehiclesTable } from '@/features/vehicles/VehiclesTable'
import { useVehicleFeed } from '@/features/vehicles/hooks'
import { useTelemetryStore } from '@/store/telemetry'

export function VehiclesPage() {
  const { data: events = [] } = useVehicleFeed()
  const selectedUnitId = useTelemetryStore((state) => state.selectedUnitId)
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const needle = query.trim()
    if (!needle) return events
    return events.filter((event) => String(event.unit_id).includes(needle))
  }, [events, query])

  const selectedEvent =
    events.find((event) => event.unit_id === selectedUnitId) ?? filtered[0]

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
          <VehiclesTable events={filtered} />
        </section>

        <section className="panel">
          <header className="panel__head">
            <h2>Разбор пакета</h2>
          </header>
          <VehicleFocus event={selectedEvent} />
        </section>
      </div>
    </div>
  )
}
