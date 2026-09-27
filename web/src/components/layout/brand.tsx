import { Link } from 'react-router-dom'

export function Logo({ to = '/dashboard' }: { to?: string }) {
  return <Link className="logo" to={to} aria-label="PromptVault home"><span className="eye-logo" aria-hidden="true"><i /></span>PROMPT<span>VAULT</span></Link>
}
