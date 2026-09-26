import axios, { AxiosError, type AxiosRequestConfig } from 'axios'

import { env } from '@/config/env'
import { useAuthStore } from '@/store/auth'

export class ApiError extends Error {
  status: number | null

  constructor(message: string, status: number | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export const http = axios.create({
  baseURL: env.apiBaseUrl,
  timeout: env.apiTimeoutMs,
  withCredentials: true,
  headers: { Accept: 'application/json' },
})

http.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (error instanceof AxiosError && error.response?.status === 401) {
      useAuthStore.getState().clearUser()
    }
    return Promise.reject(error)
  },
)

function asApiError(error: unknown): ApiError {
  if (error instanceof AxiosError) {
    const status = error.response?.status ?? null
    return new ApiError(error.response?.data?.detail ?? error.message, status)
  }
  return new ApiError(error instanceof Error ? error.message : String(error), null)
}

export async function apiGet<T>(path: string, config?: AxiosRequestConfig): Promise<T> {
  try {
    const { data } = await http.get<T>(path, config)
    return data
  } catch (error) {
    throw asApiError(error)
  }
}

export async function apiPost<TResponse, TBody>(path: string, body: TBody): Promise<TResponse> {
  try {
    const { data } = await http.post<TResponse>(path, body)
    return data
  } catch (error) {
    throw asApiError(error)
  }
}

export async function apiPostForm<TResponse>(
  path: string,
  body: URLSearchParams,
): Promise<TResponse> {
  try {
    const { data } = await http.post<TResponse>(path, body, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    return data
  } catch (error) {
    throw asApiError(error)
  }
}
