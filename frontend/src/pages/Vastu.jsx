import { useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import FloorPlan, { PlanLegend } from '../components/FloorPlan.jsx'
import VastuReport from '../components/VastuReport.jsx'
import { Alert, Button, PageHead, Spinner } from '../components/ui.jsx'
import { StepFooter } from '../components/Shell.jsx'
import { vastuAnalyze } from '../lib/api.js'
import { buildLayout, renderableFromLayout } from '../lib/layout.js'
import { useProject } from '../state/project.jsx'

export default function Vastu() {
  const { project, set, invalidate } = useProject()
  const nav = useNavigate()
  const ctrl = useRef(null)
  const { vastu } = project
  const layout = useMemo(() => buildLayout(project), [project.plan, project.furniture, project.openings, project.orientation, project.setup.roomType, project.setup.name]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async () => {
    ctrl.current?.abort(); ctrl.current = new AbortController()
    set('vastu', { status: 'running', report: null, error: null })
    invalidate('vastu')
    try {
      const report = await vastuAnalyze(layout, ctrl.current.signal)
      set('vastu', { status: 'done', report, error: null })
    } catch (e) { if (!ctrl.current.signal.aborted) set('vastu', { status: 'error', report: null, error: { message: e.message, hint: e.hint } }) }
  }
  useEffect(() => { if (vastu.status === 'idle') run(); return () => ctrl.current?.abort() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const zoneStatus = useMemo(() => {
    const m = {}
    for (const r of vastu.report?.results ?? []) {
      const z = r.observed?.zone
      if (z && r.status === 'violated') m[z] = 'bad'
      else if (z && r.status === 'satisfied' && m[z] !== 'bad') m[z] = 'good'
    }
    return m
  }, [vastu.report])

  return (
    <div className="stack" style={{ '--gap': '1.5rem' }}>
      <PageHead eyebrow="Step 7 · Vastu analysis" title="How the layout reads against traditional Vastu">A transparent check: each finding shows the rule, where your furniture actually sits (using the directions you confirmed), the reasoning, and how sure we are of the data.</PageHead>
      {vastu.status === 'running' && <Alert kind="info" title="Evaluating Vastu rules"><span className="row"><Spinner /> Checking {layout.placements.length} item(s) against the rules for a {project.setup.roomType.replace('_', ' ')}…</span></Alert>}
      {vastu.status === 'error' && <Alert kind="danger" title="The Vastu analysis failed" action={<Button size="sm" variant="ghost" onClick={run}>Retry</Button>}>{vastu.error.message} {vastu.error.hint}</Alert>}
      {vastu.status === 'done' && (
        <div className="editor">
          <div className="card stack"><VastuReport report={vastu.report} /></div>
          <div className="card plan-card sticky">
            <h4 style={{ marginTop: 0 }}>Zones on your plan</h4>
            <FloorPlan {...renderableFromLayout(layout)} showZones zoneStatus={zoneStatus} />
            <PlanLegend estimated={project.plan.room.dimensionsSource !== 'user_provided'} />
            <p className="tiny muted" style={{ margin: 0 }}>Green zones hold a satisfied rule; red zones hold a conflict. Zones use a 3×3 grid and follow the directions you confirmed.</p>
            <div className="row"><Button size="sm" variant="ghost" onClick={() => nav('/project/floorplan')}>Edit plan</Button><Button size="sm" variant="ghost" icon={<RefreshCw size={13} />} onClick={run}>Re-run</Button></div>
          </div>
        </div>
      )}
      <StepFooter back="/project/floorplan" next="/project/redesign" nextLabel="Continue to redesign" nextDisabled={vastu.status !== 'done'} hint={vastu.status === 'done' ? `${vastu.report.summary.violated} to review` : undefined} />
    </div>
  )
}
