import { useEffect, useRef, useState } from 'react'

const fmt = (v) => (v == null || v === '' || Number.isNaN(v) ? '' : String(Math.round(v * 1000) / 1000))

/**
 * Decimal input that keeps what you type (so "0." and "1.2" work) and commits every valid number.
 * Display re-syncs from `value` only while unfocused, which is when callers may have clamped it.
 */
export function NumInput({ value, onCommit, className = 'input', ...rest }) {
  const [text, setText] = useState(fmt(value))
  const focused = useRef(false)
  useEffect(() => { if (!focused.current) setText(fmt(value)) }, [value])
  return (
    <input
      {...rest} className={className} type="text" inputMode="decimal" value={text}
      onFocus={() => { focused.current = true }}
      onBlur={() => { focused.current = false; setText(fmt(value)) }}
      onChange={(e) => {
        const t = e.target.value.replace(',', '.')
        if (!/^-?\d*\.?\d*$/.test(t)) return
        setText(t)
        const n = parseFloat(t)
        if (t !== '' && !t.endsWith('.') && Number.isFinite(n)) onCommit(n)
      }}
    />
  )
}
