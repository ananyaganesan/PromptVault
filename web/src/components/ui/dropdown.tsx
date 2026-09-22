import type { ReactNode } from 'react'
export function Dropdown({ label, children }: { label: string; children: ReactNode }) { return <details><summary>{label}</summary><div className="dropdown-menu">{children}</div></details> }
