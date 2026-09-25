import axios, { AxiosError, type AxiosRequestConfig } from 'axios'

import { env } from '@/config/env'

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
  headers: { Accept: 'application/json' },
})

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
