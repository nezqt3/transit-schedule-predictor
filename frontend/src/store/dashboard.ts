import { create } from 'zustand'

import type { ReplayPrediction } from '@/types/replay'

export type DashboardSource = 'ndtp' | 'historical'

type DashboardState = {
  source: DashboardSource
  replayTimeMs: number | null
  replayRevision: number
  replayPlaying: boolean
  replaySpeed: number
  selectedReplayId: number | null
  replayPredictions: Record<string, ReplayPrediction>
  replayFailures: Record<string, string>
  setSource: (source: DashboardSource) => void
  setReplayTime: (timeMs: number) => void
  setReplayPlaying: (playing: boolean) => void
  setReplaySpeed: (speed: number) => void
  resetReplay: () => void
  selectReplayVehicle: (trId: number | null) => void
  setReplayPrediction: (prediction: ReplayPrediction) => void
  setReplayFailure: (sampleId: string, message: string) => void
}

export const useDashboardStore = create<DashboardState>((set) => ({
  source: window.localStorage.getItem('dashboard-source') === 'historical' ? 'historical' : 'ndtp',
  replayTimeMs: null,
  replayRevision: 0,
  replayPlaying: true,
  replaySpeed: 1,
  selectedReplayId: null,
  replayPredictions: {},
  replayFailures: {},
  setSource: (source) => {
    window.localStorage.setItem('dashboard-source', source)
    set((state) => source === state.source ? state : { source })
  },
  setReplayTime: (replayTimeMs) => set({ replayTimeMs }),
  setReplayPlaying: (replayPlaying) => set({ replayPlaying }),
  setReplaySpeed: (replaySpeed) => set({ replaySpeed }),
  resetReplay: () => {
    set((state) => ({
      replayTimeMs: null,
      replayRevision: state.replayRevision + 1,
      replayPlaying: true,
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
