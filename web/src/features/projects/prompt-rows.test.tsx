import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PromptRows } from './project-pages'

describe('PromptRows empty states', () => {
  it('describes an empty project as an empty library when no search is active', () => {
    render(<MemoryRouter><PromptRows projectId="project-without-prompts" /></MemoryRouter>)

    expect(screen.getByText('No prompts have been added to this project yet.')).toHaveClass('no-results')
    expect(screen.queryByText('No prompts match this search.')).not.toBeInTheDocument()
  })

  it('uses search-specific copy when a query has no matches', () => {
    render(<MemoryRouter><PromptRows search="definitely-no-such-prompt" /></MemoryRouter>)

    expect(screen.getByText('No prompts match this search.')).toHaveClass('no-results')
  })
})
