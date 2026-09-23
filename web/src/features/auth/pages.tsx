import { useState, type ChangeEvent, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Logo } from '../../components/layout/brand'
import { Button, Field } from '../../components/ui/prototype'
import { ApiClientError } from '../../lib/api/client'
import { useAuth } from './auth-context'

function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { login, register, mode: authMode } = useAuth()
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
      navigate(from && (user.role === 'super_admin' || !from.startsWith('/admin')) ? from : user.role === 'super_admin' ? '/admin' : '/dashboard', { replace: true })
    } catch (error) {
      if (error instanceof ApiClientError && error.fieldErrors) {
        const fields = error.fieldErrors
        setErrors({
          displayName: fields['body.display_name']?.join(' '),
          email: fields['body.email']?.join(' '),
          password: fields['body.password']?.join(' '),
        })
      }
      setFormError(error instanceof Error ? error.message : 'Unable to sign in.')
    }
    finally { setBusy(false) }
  }
  return <main className={mode === 'login' ? 'auth-main login-page' : 'auth-main'}><form className="auth-card" onSubmit={submit} noValidate>
    {mode === 'login' && <div className="login-logo"><Logo to="/login" /></div>}
    <h1>{mode === 'login' ? 'Welcome back' : 'Create your account'}</h1>
    <p>{mode === 'login' ? 'Sign in to access your prompts, versions, and deployments.' : 'Join PromptVault to version, collaborate, and ship better prompts.'}</p>
    {mode === 'register' && <Field label="Display name" placeholder="Your name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} error={errors.displayName} />}
    <Field label="Email address" placeholder="you@company.com" type="email" value={email} onChange={update(setEmail)} error={errors.email} />
    <Field label="Password" placeholder={mode === 'login' ? 'Enter your password' : 'Create a strong password (12+ characters, no spaces)'} type="password" value={password} onChange={update(setPassword)} error={errors.password} />
    {formError && <p className="form-error" role="alert">{formError}</p>}
    {mode === 'login' && <div className="form-row"><span>{authMode === 'demo' ? 'Demo session lasts for this tab.' : 'Session stays active in this tab after refresh.'}</span><Link to="/forgot-password">Forgot password?</Link></div>}
    <Button type="submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</Button>
    <p className="switch">{mode === 'login' ? "Don't have an account?" : 'Already have an account?'} <Link to={mode === 'login' ? '/register' : '/login'}>{mode === 'login' ? 'Register' : 'Sign in'}</Link></p>
  </form></main>
}
export function LoginPage() { return <AuthPage mode="login" /> }
export function RegisterPage() { return <AuthPage mode="register" /> }
export function ForgotPasswordPage() { const [sent, setSent] = useState(false); return <main className="auth-main"><div className="auth-card"><h1>Forgot password?</h1><p>{sent ? 'This is a prototype: no email was sent. Contact an administrator to restore access.' : 'Password recovery is not connected in this prototype.'}</p>{!sent && <Button onClick={() => setSent(true)}>How do I regain access?</Button>}<p className="switch"><Link to="/login">Back to sign in</Link></p></div></main> }
