import { LockKeyhole } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { env } from '@/config/env'
import { getCurrentUser, login } from '@/features/auth/api'
import { ApiError } from '@/lib/api/http'
import { useAuthStore } from '@/store/auth'

type LoginLocationState = { from?: string }

export function LoginPage() {
  const user = useAuthStore((state) => state.user)
  const setUser = useAuthStore((state) => state.setUser)
  const location = useLocation()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (user) return <Navigate replace to="/" />

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await login(username, password)
      setUser(await getCurrentUser())
      const state = location.state as LoginLocationState | null
      navigate(state?.from ?? '/', { replace: true })
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 401
          ? 'Неверный логин или пароль'
          : 'Не удалось связаться с Backend',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="login-card__icon"><LockKeyhole size={24} /></div>
        <div>
          <h1>{env.appName}</h1>
          <p>Войдите под учётной записью диспетчера</p>
        </div>
        <label className="login-field">
          <span>Логин</span>
          <input
            autoComplete="username"
            autoFocus
            onChange={(event) => setUsername(event.target.value)}
            required
            value={username}
          />
        </label>
        <label className="login-field">
          <span>Пароль</span>
          <input
            autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>
        {error && <p className="login-card__error" role="alert">{error}</p>}
        <button disabled={isSubmitting} type="submit">
          {isSubmitting ? 'Входим…' : 'Войти'}
        </button>
      </form>
    </main>
  )
}
