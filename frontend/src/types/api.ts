/** Зеркалирует backend/app/ndtp/schemas.py. */

export type NavData = {
  timestamp: number
  latitude: number
  longitude: number
  coordinates_valid: boolean
  speed_avg: number | null
  speed_max: number | null
  course: number | null
  track_m: number | null
  altitude_m: number | null
  satellites: number | null
  battery_voltage_mv: number | null
  alert_flag: boolean
  sos_flag: boolean
}

export type CanData = {
  speed_kmh: number | null
  engine_rpm: number | null
  engine_temp_c: number | null
  odometer_km: number | null
  engine_hours: number | null
  alarm_flags: number
}

export type TelemetryEvent = {
  unit_id: number
  received_at: string
  nav: NavData | null
  can: CanData | null
}

/** Зеркалирует backend/app/schemas/prediction.py. */

export type PredictionRequest = {
  tr_id: number
  timestamp: string
  lat: number
  lon: number
  speed: number
  cur_dev_s: number
}

export type PredictionResponse = {
  tr_id: number
  prediction: number
  model_version: string
}

export type HealthResponse = {
  status: string
  service: string
}

export type TokenResponse = {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

export type CurrentUser = {
  username: string
  role: 'dispatcher'
}
