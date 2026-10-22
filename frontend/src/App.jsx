import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { ProjectProvider, useProject } from './state/project.jsx'
import { WizardLayout } from './components/Shell.jsx'
import { STEPS, blocker } from './lib/steps.js'
import Landing from './pages/Landing.jsx'
import Setup from './pages/Setup.jsx'
import Photos from './pages/Photos.jsx'
import Orientation from './pages/Orientation.jsx'
import Furniture from './pages/Furniture.jsx'
import Analyze from './pages/Analyze.jsx'
import FloorPlanPage from './pages/FloorPlanPage.jsx'
import Vastu from './pages/Vastu.jsx'
import Redesign from './pages/Redesign.jsx'
import Results from './pages/Results.jsx'
import { Alert } from './components/ui.jsx'

const PAGES = {
  '/project/setup': Setup, '/project/photos': Photos, '/project/orientation': Orientation, '/project/furniture': Furniture,
  '/project/analyze': Analyze, '/project/floorplan': FloorPlanPage, '/project/vastu': Vastu, '/project/redesign': Redesign, '/project/results': Results,
}

/** Redirects to the first unmet step instead of rendering a page that would have nothing to show. */
function Guard({ path, children }) {
  const { project } = useProject()
  const why = blocker(path, project)
  if (!why) return children
  const i = STEPS.findIndex((s) => blocker(s.path, project))
  return <Navigate to={STEPS[Math.max(0, i)].path} replace state={{ why }} />
}

function Notice() {
  const { state } = useLocation()
  return state?.why ? <div style={{ marginBottom: '1rem' }}><Alert kind="info" title="One step at a time">{state.why}</Alert></div> : null
}

export default function App() {
  return (
    <ProjectProvider>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/project" element={<WizardLayout />}>
          <Route index element={<Navigate to="/project/setup" replace />} />
          {STEPS.map((s) => { const Page = PAGES[s.path]; return <Route key={s.path} path={s.path.replace('/project/', '')} element={<Guard path={s.path}><Notice /><Page /></Guard>} /> })}
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ProjectProvider>
  )
}
