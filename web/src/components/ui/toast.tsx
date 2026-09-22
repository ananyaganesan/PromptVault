import type { ReactNode } from 'react'
export function Toast({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'success' | 'warning' | 'danger' }) { return <div className={`toast ${tone}`} role="status">{children}</div> }
