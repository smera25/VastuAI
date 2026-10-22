import { useState } from 'react'
import { CheckCircle2, HelpCircle, TriangleAlert } from 'lucide-react'
import { ZONE_LABEL, DIRECTION_LABEL } from '../lib/orientation.js'
import { Chip } from './ui.jsx'

const CONF = { user_confirmed: ['sage', 'Based on your confirmed data'], estimated: ['warn', 'Based on estimated data'], unverified: ['dashed', 'Unverified data'] }

function Observed({ r }) {
  const o = r.observed
  if (!o) return null
  if (o.zone) return <>{r.subject?.label ?? 'It'} is in the <strong>{ZONE_LABEL[o.zone]}</strong> zone</>
  if (o.zones) return <>Windows are in: <strong>{o.zones.map((z) => ZONE_LABEL[z]).join(', ')}</strong></>
  if (o.direction) return <>Points toward <strong>{DIRECTION_LABEL[o.direction]}</strong></>
  if (o.gap_m != null) return <>Gap between them: <strong>{o.gap_m} m</strong></>
  return null
}

function Expected({ r }) {
  const e = r.expected
  if (!e) return null
  const fmt = (arr) => arr.map((z) => ZONE_LABEL[z] ?? DIRECTION_LABEL[z] ?? z).join(', ')
  return (
    <span className="small muted">
      {e.preferred && <>Preferred: {fmt(e.preferred)}. </>}
      {e.avoid?.length > 0 && <>Avoid: {fmt(e.avoid)}. </>}
      {e.min_gap_m != null && <>Minimum gap: {e.min_gap_m} m.</>}
    </span>
  )
}

function Finding({ r }) {
  const [open, setOpen] = useState(r.status !== 'satisfied')
  const meta = {
    satisfied: { icon: <CheckCircle2 size={18} color="var(--ok)" />, chip: ['ok', 'Satisfied'] },
    violated: { icon: <TriangleAlert size={18} color={r.severity === 'major' ? 'var(--danger)' : 'var(--warn)'} />, chip: [r.severity === 'major' ? 'danger' : 'warn', r.severity === 'major' ? 'Needs attention' : 'Could improve'] },
    indeterminate: { icon: <HelpCircle size={18} color="var(--info)" />, chip: ['info', 'Can’t tell yet'] },
  }[r.status]
  const [cc, cl] = CONF[r.evidence?.confidence] ?? []
  return (
    <article className={`finding ${r.status}`} data-rule={r.rule_id}>
      <button className="finding-head" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {meta.icon}
        <span className="finding-title">{r.title}{r.subject?.label && <span className="muted"> · {r.subject.label}</span>}</span>
        <Chip kind={meta.chip[0]}>{meta.chip[1]}</Chip>
        {r.category === 'practical' && <Chip kind="dashed">Practical, not Vastu</Chip>}
      </button>
      {open && (
        <div className="finding-body">
          {r.status !== 'indeterminate' && <p><Observed r={r} /> <Expected r={r} /></p>}
          {r.detail && <p>{r.detail}</p>}
          <p className="small"><strong>Why:</strong> {r.reason}</p>
          {r.consensus && <p className="small muted">Agreement: {r.consensus}</p>}
          {r.recommendation && <p className="recommend"><strong>{r.status === 'indeterminate' ? 'To check this: ' : 'Suggestion: '}</strong>{r.recommendation}</p>}
          <div className="row">{cc && <Chip kind={cc}>{cl}</Chip>}{r.requires_confirmation && <Chip kind="warn">Please confirm before acting</Chip>}</div>
        </div>
      )}
    </article>
  )
}

export default function VastuReport({ report }) {
  const { summary, results, room_summary: room } = report
  const groups = [
    ['Needs attention', results.filter((r) => r.status === 'violated')],
    ['Missing information', results.filter((r) => r.status === 'indeterminate')],
    ['Satisfied', results.filter((r) => r.status === 'satisfied')],
  ]
  return (
    <div className="stack" style={{ '--gap': '1.25rem' }}>
      <div className="grid cols-3 stats">
        <div className="stat"><b>{summary.satisfied}</b><span>satisfied</span></div>
        <div className="stat"><b className={summary.violated ? 'bad' : ''}>{summary.violated}</b><span>to review</span></div>
        <div className="stat"><b>{summary.indeterminate}</b><span>can’t tell yet</span></div>
      </div>
      <p className="small muted">{summary.note}</p>
      <div className="card soft small">
        <strong>Room summary.</strong> {room.name ? `${room.name} — ` : ''}{room.room_type.replace('_', ' ')}, {room.dimensions_metres.width} × {room.dimensions_metres.length} m
        {room.dimensions_source !== 'user_provided' && ' (estimated)'}. {room.orientation_note}{' '}
        {room.furniture_count} item{room.furniture_count === 1 ? '' : 's'}, {room.openings.doors} door{room.openings.doors === 1 ? '' : 's'}, {room.openings.windows} window{room.openings.windows === 1 ? '' : 's'}.
      </div>
      {groups.map(([name, list]) => list.length > 0 && (
        <section key={name} aria-label={name}>
          <h3 className="group-title">{name} <span className="muted">({list.length})</span></h3>
          <div className="stack" style={{ '--gap': '.6rem' }}>{list.map((r, i) => <Finding key={`${r.rule_id}-${r.subject?.id ?? i}`} r={r} />)}</div>
        </section>
      ))}
      <p className="small muted disclaimer">{report.disclaimer}</p>
    </div>
  )
}
