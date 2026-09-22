import type { SelectHTMLAttributes } from 'react'
export function Select({ label, children, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) { return <label className="field">{label && <span>{label}</span>}<select {...props}>{children}</select></label> }
