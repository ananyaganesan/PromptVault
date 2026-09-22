import type { InputHTMLAttributes } from 'react'
export function SearchInput(props: InputHTMLAttributes<HTMLInputElement>) { return <input type="search" className="search-input" aria-label="Search" placeholder="Search…" {...props}/> }
