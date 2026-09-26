function positiveNumber(raw: string | undefined, fallback: number): number {
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

export const env = {
  appName: import.meta.env.VITE_APP_NAME ?? 'Сигнальная сетка',
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  apiTimeoutMs: positiveNumber(import.meta.env.VITE_API_TIMEOUT_MS, 5_000),
  pollIntervalMs: positiveNumber(import.meta.env.VITE_POLL_INTERVAL_MS, 3_000),
  mapStyleUrl: import.meta.env.VITE_MAP_STYLE_URL || null,
} as const
