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
