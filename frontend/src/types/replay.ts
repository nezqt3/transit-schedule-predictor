export type ReplayVehicle = {
  tr_id: number
  unit_id: number
  samples: number
  start_at: string
  end_at: string
}

export type ReplayTelemetry = {
  available_at: string
  event_time: string
  lat: number
  lon: number
  speed: number | null
  heading: number | null
}

export type ReplayStop = {
  stop_id: number
  planned_at: string
  lat: number
  lon: number
  place_id: string
  address: string | null
  gps_confirmed: boolean
  gps_distance_m: number | null
}

export type ReplayPoint = {
  sample_id: string
  T: string
  target_stop_id: number
  target_time_begin: string
  cur_dev_s: number
  actual_delay_s: number
  actual_at: string
  lat: number
  lon: number
}

export type ReplayScenario = {
  source: 'historical_csv_test'
  vehicle: ReplayVehicle
  telemetry: ReplayTelemetry[]
  stops: ReplayStop[]
  points: ReplayPoint[]
}

export type ReplayPrediction = {
  sample_id: string
  predicted_delay_s: number
  baseline_delay_s: number
  model_version: string
}

export type ReplayRun = {
  run_id: string
  tr_id: number
  start_at: string
  end_at: string
  stop_ids: number[]
  confirmed_stops: number
  valid: boolean
}

export type ReplayFleetVehicle = {
  tr_id: number
  unit_id: number
  telemetry: ReplayTelemetry[]
  stops: ReplayStop[]
  runs: ReplayRun[]
  points: ReplayPoint[]
}

export type ReplayFleet = {
  source: 'historical_csv_test'
  start_at: string
  end_at: string
  vehicles: ReplayFleetVehicle[]
}

export type ReplayStreamStatus = {
  state: string
  source_at: string | null
  time_mode: string | null
  speed_multiplier: number
  sent_packets: number
  total_packets: number
}
