import type { ReactNode } from 'react'
export function Tabs({ children }: { children: ReactNode }) { return <div className="tabs">{children}</div> }
export function Tab({ children, active, onClick }: { children: ReactNode; active?: boolean; onClick?: () => void }) { return <button className={active ? 'selected' : ''} onClick={onClick}>{children}</button> }
