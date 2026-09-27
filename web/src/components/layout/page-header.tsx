import type { ReactNode } from 'react'
export function PageHeader({ title, description, eyebrow = 'WORKSPACE', action }: { title: string; description?: string; eyebrow?: string; action?: ReactNode }) { return <div className="page-header"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div> }
