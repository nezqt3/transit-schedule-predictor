import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { formatClock } from '@/lib/format/time'
import type { SpeedPoint } from '@/store/telemetry'

type SpeedTrendProps = {
  points: readonly SpeedPoint[]
}

export function SpeedTrend({ points }: SpeedTrendProps) {
  if (points.length < 2) {
    return <p className="panel__hint">История скорости накопится за пару циклов опроса.</p>
  }

  return (
    <div className="chart">
      <ResponsiveContainer height={180} width="100%">
        <AreaChart data={points as SpeedPoint[]} margin={{ bottom: 4, left: -18, right: 4, top: 8 }}>
          <defs>
            <linearGradient id="speedFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.55} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--border)" strokeDasharray="2 6" vertical={false} />
          <XAxis
            dataKey="timeMs"
            stroke="var(--text-muted)"
            tickFormatter={formatClock}
            tick={{ fontSize: 11 }}
          />
          <YAxis stroke="var(--text-muted)" tick={{ fontSize: 11 }} width={44} />
          <Tooltip
            contentStyle={{
              background: 'var(--surface-raised)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              fontSize: 12,
            }}
            labelFormatter={(value) => formatClock(Number(value))}
            formatter={(value) => [`${Number(value).toFixed(1)} км/ч`, 'скорость']}
          />
          <Area
            fill="url(#speedFill)"
            stroke="var(--accent)"
            strokeWidth={2}
            type="monotone"
            dataKey="speed"
            isAnimationActive={false}
            name="скорость"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
