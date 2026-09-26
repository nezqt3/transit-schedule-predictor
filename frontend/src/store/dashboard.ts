import { create } from 'zustand'

import type { ReplayPrediction } from '@/types/replay'

export type DashboardSource = 'ndtp' | 'historical'
export const REPLAY_ANCHOR_KEY = 'january-replay-anchor-ms'

type DashboardState = {
  source: DashboardSource
  replayTimeMs: number | null
  replayRevision: number
  selectedReplayId: number | null
  replayPredictions: Record<string, ReplayPrediction>
  replayFailures: Record<string, string>
  setSource: (source: DashboardSource) => void
  setReplayTime: (timeMs: number) => void
  resetReplay: () => void
  selectReplayVehicle: (trId: number | null) => void
  setReplayPrediction: (prediction: ReplayPrediction) => void
  setReplayFailure: (sampleId: string, message: string) => void
}

export const useDashboardStore = create<DashboardState>((set) => ({
  source: window.localStorage.getItem('dashboard-source') === 'historical' ? 'historical' : 'ndtp',
  replayTimeMs: null,
  replayRevision: 0,
  selectedReplayId: null,
  replayPredictions: {},
  replayFailures: {},
  setSource: (source) => {
    window.localStorage.setItem('dashboard-source', source)
    set((state) => source === state.source ? state : { source })
  },
  setReplayTime: (replayTimeMs) => set({ replayTimeMs }),
  resetReplay: () => {
    window.localStorage.setItem(REPLAY_ANCHOR_KEY, String(Date.now()))
    set((state) => ({
      replayTimeMs: null,
      replayRevision: state.replayRevision + 1,
      selectedReplayId: null,
      replayPredictions: {},
      replayFailures: {},
    }))
  },
  selectReplayVehicle: (selectedReplayId) => set({ selectedReplayId }),
  setReplayPrediction: (prediction) => set((state) => ({
    replayPredictions: { ...state.replayPredictions, [prediction.sample_id]: prediction },
  })),
  setReplayFailure: (sampleId, message) => set((state) => ({
    replayFailures: { ...state.replayFailures, [sampleId]: message },
  })),
}))
