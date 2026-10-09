import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { telemetry } from '../services/telemetry'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError(null)

    try {
      await login({ email, password })

      // login_succeeded is tracked inside AuthContext after getMe resolves
      // with the actual user role from the backend response.
      navigate('/suppliers')
    } catch (err) {
      // Track login failure — frontend cannot distinguish email_not_found from
      // wrong_password, so we use frontend-safe reasons
      const failure_reason =
        err instanceof TypeError ? 'network_error' : 'invalid_credentials'
      telemetry.track('login_failed', { failure_reason })

      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <p className="eyebrow">TrackFlow Operations</p>
          <h1>Sign in</h1>
          <p className="subtitle">
            Enter your credentials to access the supplier directory.
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <label>
            Email
            <input
              required
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>

          <label>
            Password
            <input
              required
              type="password"
              placeholder="Your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Link to="/forgot-password" className="auth-forgot-link">
              ¿Olvidaste tu contraseña?
            </Link>
          </label>

          {error && <div className="auth-error">{error}</div>}

          <button className="primary-button auth-button" disabled={busy} type="submit">
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="auth-alt">
          Don't have an account? <Link to="/register">Create one</Link>.
        </p>
      </div>
    </main>
  )
}