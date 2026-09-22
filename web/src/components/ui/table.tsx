import type { ReactNode } from 'react'
export function DataTable({ children }: { children: ReactNode }) { return <div className="table-panel panel"><table>{children}</table></div> }
