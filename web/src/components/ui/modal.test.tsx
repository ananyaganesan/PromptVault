import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Modal } from './modal'

describe('Modal keyboard access', () => {
  it('moves focus into the dialog, traps Tab, closes with Escape, and restores focus', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const view = render(<><button>Open dialog</button><Modal open={false} title="Confirm action" onClose={onClose}><button>Confirm</button></Modal></>)
    screen.getByRole('button', { name: 'Open dialog' }).focus()
    view.rerender(<><button>Open dialog</button><Modal open title="Confirm action" onClose={onClose}><button>Confirm</button></Modal></>)
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus()
    await user.keyboard('{Shift>}{Tab}{/Shift}')
    expect(screen.getByRole('button', { name: 'Confirm' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
    view.rerender(<><button>Open dialog</button><Modal open={false} title="Confirm action" onClose={onClose}><button>Confirm</button></Modal></>)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open dialog' })).toHaveFocus()
  })
})
