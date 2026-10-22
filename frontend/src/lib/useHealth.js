import { useEffect, useState } from 'react'
import { getHealth } from './api.js'

let cached = null
/** Backend capability report (VGGT / YOLO / image generation) - fetched once per page load. */
export function useHealth() {
  const [state, setState] = useState(cached ?? { status: 'loading', data: null, error: null })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (cached && attempt === 0) return
    const ctrl = new AbortController()
    getHealth(ctrl.signal)
      .then((data) => { cached = { status: 'ok', data, error: null }; setState(cached) })
      .catch((error) => { if (!ctrl.signal.aborted) setState({ status: 'error', data: null, error }) })
    return () => ctrl.abort()
  }, [attempt])
  return { ...state, retry: () => { cached = null; setState({ status: 'loading', data: null, error: null }); setAttempt((a) => a + 1) } }
}
