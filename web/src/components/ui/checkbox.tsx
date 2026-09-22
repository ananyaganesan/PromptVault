import type { InputHTMLAttributes } from 'react'
export function Checkbox({ label, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string }) { return <label className="check"><input type="checkbox" {...props}/>{label}</label> }
