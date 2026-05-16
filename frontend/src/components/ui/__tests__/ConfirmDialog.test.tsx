import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'

import ConfirmDialog from '../ConfirmDialog'

describe('ConfirmDialog', () => {
  it('renders title, body, and both buttons when open', () => {
    render(
      <ConfirmDialog
        isOpen={true}
        onClose={() => {}}
        onConfirm={() => {}}
        title="Delete this settlement?"
        body="Are you sure?"
      />,
    )
    expect(screen.getByText('Delete this settlement?')).toBeInTheDocument()
    expect(screen.getByText('Are you sure?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })

  it('calls onConfirm when the confirm button is clicked', () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        isOpen={true}
        onClose={() => {}}
        onConfirm={onConfirm}
        title="Delete?"
        body="body"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when the cancel button is clicked', () => {
    const onClose = vi.fn()
    render(
      <ConfirmDialog
        isOpen={true}
        onClose={onClose}
        onConfirm={() => {}}
        title="Delete?"
        body="body"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('disables confirm and renders a spinner when isLoading is true', () => {
    render(
      <ConfirmDialog
        isOpen={true}
        onClose={() => {}}
        onConfirm={() => {}}
        title="Delete?"
        body="body"
        isLoading={true}
      />,
    )
    const confirmBtn = screen.getByRole('button', { name: /Delete/i })
    expect(confirmBtn).toBeDisabled()
    expect(screen.getByTestId('confirm-spinner')).toBeInTheDocument()
  })
})
