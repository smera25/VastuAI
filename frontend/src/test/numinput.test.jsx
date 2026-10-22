import { useState } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { NumInput } from '../components/NumInput.jsx'

function Harness({ clampMax = 99 }) {
  const [v, setV] = useState(0.85)
  return <><NumInput aria-label="n" value={v} onCommit={(n) => setV(Math.min(n, clampMax))} /><output data-testid="v">{v}</output></>
}
const type = (el, text) => { fireEvent.focus(el); for (const ch of ['', ...text.split('').map((_, i) => text.slice(0, i + 1))]) fireEvent.change(el, { target: { value: ch } }) }

describe('NumInput', () => {
  it('lets you type decimals like 0.5 and 1.2 (regression: trailing "." was eaten)', () => {
    render(<Harness />)
    const el = screen.getByLabelText('n')
    type(el, '0.5'); expect(el.value).toBe('0.5'); expect(screen.getByTestId('v').textContent).toBe('0.5')
    type(el, '1.25'); expect(el.value).toBe('1.25'); expect(screen.getByTestId('v').textContent).toBe('1.25')
  })
  it('accepts a decimal comma and rejects letters', () => {
    render(<Harness />)
    const el = screen.getByLabelText('n'); fireEvent.focus(el)
    fireEvent.change(el, { target: { value: '2,5' } }); expect(el.value).toBe('2.5')
    fireEvent.change(el, { target: { value: '2.5abc' } }); expect(el.value).toBe('2.5')
  })
  it('shows the clamped value after blur', () => {
    render(<Harness clampMax={1.7} />)
    const el = screen.getByLabelText('n'); type(el, '3'); fireEvent.blur(el)
    expect(el.value).toBe('1.7')
  })
})
