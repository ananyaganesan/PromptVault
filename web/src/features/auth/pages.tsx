import { useState, type ChangeEvent, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { Logo } from '../../components/layout/brand'
import { Button, Field } from '../../components/ui/prototype'
import { ApiClientError } from '../../lib/api/client'
import { useAuth } from './auth-context'
import { authApi } from './api'

function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { login, register } = useAuth()
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<{ displayName?: string; email?: string; password?: string }>({})
  const [formError, setFormError] = useState('')
  const [busy, setBusy] = useState(false)
  const update = (setter: (value: string) => void) => (event: ChangeEvent<HTMLInputElement>) => setter(event.target.value.replace(/\s/g, ''))
  async function submit(event: FormEvent) {
    event.preventDefault()
    const next: typeof errors = {}
    if (mode === 'register' && !displayName.trim()) next.displayName = 'Display name is required.'
    if (!email) next.email = 'Email address is required.'
    else if (!/^\S+@\S+\.\S+$/.test(email)) next.email = 'Enter a valid email address.'
    if (!password) next.password = 'Password is required.'
    else if (mode === 'register' && password.length < 12) next.password = 'Use at least 12 characters.'
    setErrors(next)
    setFormError('')
    if (Object.keys(next).length) return
    setBusy(true)
    try {
      const user = mode === 'register' ? await register({ display_name: displayName.trim(), email: email.trim(), password }) : await login({ email: email.trim(), password })
      const from = (location.state as { from?: string } | null)?.from
      const requestedRoute = from?.startsWith('/') && !from.startsWith('//') && (user.role === 'super_admin' || !from.startsWith('/admin'))
        ? from
        : null
      navigate(requestedRoute ?? (mode === 'register' && user.role === 'super_admin' ? '/admin' : '/dashboard'), { replace: true })
    } catch (error) {
      if (error instanceof ApiClientError && error.fieldErrors) {
        const fields = error.fieldErrors
        setErrors({
          displayName: fields['body.display_name']?.join(' '),
          email: fields['body.email']?.join(' '),
          password: fields['body.password']?.join(' '),
        })
      }
      setFormError(mode === 'login' && error instanceof ApiClientError && error.status === 401
        ? 'Invalid email or password.'
        : error instanceof Error && error.message === 'Failed to fetch'
          ? 'Unable to connect to the server. Please try again.'
          : error instanceof Error ? error.message : 'Unable to sign in.')
    }
    finally { setBusy(false) }
  }
  return <main className="auth-main"><form className="auth-card" onSubmit={submit} noValidate>
    {mode === 'login' && <div className="login-logo"><Logo to="/login" /></div>}
    <h1>{mode === 'login' ? 'Welcome back' : 'Create your account'}</h1>
    <p>{mode === 'login' ? 'Sign in to access your prompts, versions, and deployments.' : 'Join PromptVault to version, collaborate, and ship better prompts.'}</p>
    {mode === 'register' && <Field label="Display name" placeholder="Your name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} error={errors.displayName} />}
    <Field label="Email address" placeholder="you@company.com" type="email" value={email} onChange={update(setEmail)} error={errors.email} />
    <Field label="Password" placeholder={mode === 'login' ? 'Enter your password' : 'Create a strong password (12+ characters, no spaces)'} type="password" value={password} onChange={mode === 'login' ? (event) => setPassword(event.target.value) : update(setPassword)} error={errors.password} />
    {formError && <p className="form-error" role="alert">{formError}</p>}
    {mode === 'login' && <div className="form-row"><span /><Link to="/forgot-password">Forgot password?</Link></div>}
    <Button type="submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</Button>
    <p className="switch">{mode === 'login' ? "Don't have an account?" : 'Already have an account?'} <Link to={mode === 'login' ? '/register' : '/login'}>{mode === 'login' ? 'Register' : 'Sign in'}</Link></p>
  </form></main>
}
export function LoginPage() { return <AuthPage mode="login" /> }
export function RegisterPage() { return <AuthPage mode="register" /> }

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const normalizedEmail = email.trim().toLowerCase()
    if (!/^\S+@\S+\.\S+$/.test(normalizedEmail)) {
      setError('Enter a valid email address.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await authApi.requestPasswordReset(normalizedEmail)
      setSent(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to send reset email.')
    } finally {
      setBusy(false)
    }
  }

  return <main className="auth-main"><form className="auth-card" onSubmit={submit} noValidate><h1>Reset your password</h1><p>{sent ? 'If this email belongs to an active account, a reset link has been sent. Check your inbox.' : 'Enter your email address and we will send a one-time password reset link.'}</p>{!sent && <><Field label="Email address" placeholder="you@company.com" type="email" value={email} onChange={(event) => setEmail(event.target.value.replace(/\s/g, ''))} error={error} />{error && <p className="form-error" role="alert">{error}</p>}<Button type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send reset link'}</Button></>}<p className="switch"><Link to="/login">Back to sign in</Link></p></form></main>
}

export function ResetPasswordPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [complete, setComplete] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!token) return setError('This password reset link is invalid.')
    if (password.length < 12) return setError('Use at least 12 characters.')
    if (/\s/.test(password)) return setError('Password must not contain spaces.')
    if (password !== confirmPassword) return setError('Passwords do not match.')
    setBusy(true)
    setError('')
    try {
      await authApi.confirmPasswordReset(token, password)
      setComplete(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to reset password.')
    } finally {
      setBusy(false)
    }
  }

  return <main className="auth-main"><form className="auth-card" onSubmit={submit} noValidate><h1>Choose a new password</h1><p>{complete ? 'Your password has been reset. You can now sign in.' : 'Use at least 12 characters with no spaces. Choose a password you have never used for this account.'}</p>{!complete && <><Field label="New password" placeholder="Create a strong password" type="password" value={password} onChange={(event) => setPassword(event.target.value.replace(/\s/g, ''))} /><Field label="Confirm password" placeholder="Repeat your new password" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value.replace(/\s/g, ''))} />{error && <p className="form-error" role="alert">{error}</p>}<Button type="submit" disabled={busy}>{busy ? 'Resetting…' : 'Reset password'}</Button></>}{complete && <Button type="button" onClick={() => navigate('/login')}>Sign in</Button>}<p className="switch"><Link to="/login">Back to sign in</Link></p></form></main>
}
