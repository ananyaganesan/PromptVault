import type { ButtonHTMLAttributes } from 'react'
type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger'; loading?: boolean }
export function Button({ variant = 'primary', loading = false, disabled, children, className = '', ...props }: Props) { return <button className={`button ${variant !== 'primary' ? variant : ''} ${className}`.trim()} disabled={disabled || loading} {...props}>{loading ? 'Loading…' : children}</button> }
