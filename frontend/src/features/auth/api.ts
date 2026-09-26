import { apiGet, apiPost, apiPostForm } from '@/lib/api/http'
import type { CurrentUser, TokenResponse } from '@/types/api'

export function login(username: string, password: string): Promise<TokenResponse> {
  const form = new URLSearchParams({ username, password })
  return apiPostForm<TokenResponse>('/auth/token', form)
}

export function getCurrentUser(): Promise<CurrentUser> {
  return apiGet<CurrentUser>('/auth/me')
}

export function logout(): Promise<void> {
  return apiPost<void, Record<string, never>>('/auth/logout', {})
}
