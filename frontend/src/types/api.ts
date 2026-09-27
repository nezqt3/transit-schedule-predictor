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

export type TelemetryStreamMessage =
  | { type: 'vehicle_snapshot'; data: TelemetryEvent[] }
  | { type: 'vehicle_update'; data: TelemetryEvent }
  | { type: 'prediction_update'; data: StoredPrediction }
  | { type: 'incident'; data: Incident }
  | { type: 'heartbeat' }

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

export type StoredPrediction = {
  tr_id: number
  unit_id: number
  prediction_time: string
  input_event_time?: string | null
  input_received_at?: string | null
  target_stop_id: number
  target_time: string
  current_delay_s: number
  predicted_delay_s: number
  model_version: string
  model?: string | null
  model_artifact_sha256?: string | null
  produced_at?: string | null
  predicted_arrival?: string | null
  current_delay_source?: string
  last_confirmed_stop_id?: number | null
  last_confirmed_at?: string | null
  source?: 'live' | 'replay' | 'manual' | 'demo'
  p_late?: number | null
  risk_model_version?: string | null
  risk?: 'low' | 'medium' | 'high'
  risk_source?: string
  freshness?: 'fresh' | 'stale' | 'unavailable'
}

export type PredictionStatus = {
  unit_id: number
  tr_id: number | null
  code: string
  updated_at: string
}

export type Incident = {
  incident_id: string
  tr_id: number
  unit_id: number
  target_stop_id: number
  target_time: string
  previous_stop_id: number | null
  segment: string
  predicted_delay_s: number
  p_late: number | null
  risk: 'medium' | 'high'
  risk_source: string
  cause: string
  evidence: string
  recommendation: string
  status: 'active' | 'resolved'
  created_at: string
  updated_at: string
}

export type WhatIfVehicle = {
  tr_id: number
  predicted_delay_s: number
  run_id?: string | null
  target_stop_id?: number | null
  passenger_count?: number
  vehicle_capacity?: number
  remaining_trip_minutes?: number
  next_run_departure_minutes?: number | null
  turnaround_minutes?: number
  rotation_runs?: WhatIfRotationRun[]
}

export type WhatIfRotationRun = {
  run_id: string
  departure_minutes: number
  duration_minutes: number
  turnaround_minutes?: number | null
}

export type WhatIfRequest = {
  vehicles: WhatIfVehicle[]
  additional_vehicles: number
  dispatch_lead_minutes: number
  late_threshold_s: number
  traffic_multiplier: number
  reserve_capacity: number
  passenger_transfer_minutes: number
}

export type WhatIfMetrics = {
  average_delay_s: number
  maximum_delay_s: number
  late_runs: number
  on_time_runs: number
  passenger_delay_minutes: number
  affected_passengers: number
  missed_next_runs: number
  rotation_delay_s: number
}

export type WhatIfAssignment = {
  reserve_vehicle: number
  tr_id: number
  run_id: string | null
  target_stop_id: number | null
  before_delay_s: number
  after_delay_s: number
  reduction_s: number
  passenger_count: number
  served_passengers: number
  overflow_passengers: number
  passenger_delay_reduction_minutes: number
  downstream_delay_reduction_s: number
  traffic_adjusted_delay_s: number
  rotation_feasible: boolean
}

export type WhatIfResponse = {
  baseline: WhatIfMetrics
  scenario: WhatIfMetrics
  assignments: WhatIfAssignment[]
  total_delay_reduction_s: number
  total_passenger_delay_reduction_minutes: number
  total_downstream_delay_reduction_s: number
  methodology: string
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
