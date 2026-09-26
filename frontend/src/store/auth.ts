import { create } from 'zustand'

import type { CurrentUser } from '@/types/api'

type AuthState = {
  user: CurrentUser | null
  isReady: boolean
  setUser: (user: CurrentUser) => void
  clearUser: () => void
  finishRestore: (user: CurrentUser | null) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isReady: false,
  setUser: (user) => set({ user, isReady: true }),
  clearUser: () => set({ user: null, isReady: true }),
  finishRestore: (user) => set({ user, isReady: true }),
}))
