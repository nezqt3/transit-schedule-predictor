import { formatDistanceToNowStrict } from 'date-fns'
import { ru } from 'date-fns/locale'

export function formatClock(value: string | number): string {
  return new Date(value).toLocaleTimeString('ru-RU', {
    timeZone: 'Europe/Moscow',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function formatShortClock(value: string | number): string {
  return formatClock(value).slice(0, 5)
}

export function formatDelay(seconds: number): string {
  const rounded = Math.round(Math.abs(seconds))
  const sign = rounded === 0 ? '' : seconds > 0 ? '+' : '−'
  const minutes = Math.floor(rounded / 60)
  const rest = rounded % 60
  return minutes ? `${sign}${minutes} мин${rest ? ` ${rest} с` : ''}` : `${sign}${rest} с`
}

export function formatDateTime(value: string | number): string {
  return new Date(value).toLocaleString('ru-RU', {
    timeZone: 'Europe/Moscow',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function formatAge(value: string | number): string {
  return formatDistanceToNowStrict(new Date(value), {
    locale: ru,
    roundingMethod: 'floor',
  })
}
