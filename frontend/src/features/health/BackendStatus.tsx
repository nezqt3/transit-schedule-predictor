import { Signal, WifiOff } from 'lucide-react'

import { cn } from '@/lib/cn'

import { useHealth } from './api'

export function BackendStatus() {
  const { data, isPending, isError } = useHealth()

  const state = isError ? 'error' : isPending ? 'pending' : 'ok'
  const label =
    state === 'ok' && data ? 'Backend доступен' :
    state === 'pending' ? 'Подключение…' : 'Backend недоступен'

  return (
    <span className={cn('backend-status', `backend-status--${state}`)}>
      {state === 'error' ? <WifiOff size={14} /> : <Signal size={14} />}
      <span>{label}</span>
    </span>
  )
}
