import { useNavigate } from 'react-router-dom'
import { ArrowRight, Camera, Compass, LayoutDashboard, Sparkles } from 'lucide-react'
import { Header } from '../components/Shell.jsx'
import FloorPlan from '../components/FloorPlan.jsx'
import { Button } from '../components/ui.jsx'
import { useProject } from '../state/project.jsx'
import { furthestStep, STEPS } from '../lib/steps.js'

// Decorative marketing illustration only (clearly captioned); it is never shown as a result.
const ILLUSTRATION = {
  width: 4.4, length: 3.6, topEdgeDirection: 'east',
  openings: [{ id: 'a', type: 'door', wall: 'bottom', offset: 3.2, width: 0.9, is_main_entrance: true }, { id: 'b', type: 'window', wall: 'top', offset: 1.4, width: 1.5 }],
  placements: [
    { id: 'p1', item: 'bed', label: 'Bed', x: 2.4, y: 1.0, width: 2.0, length: 1.6, headboardEdge: 'right' },
    { id: 'p2', item: 'wardrobe', label: 'Wardrobe', x: 0.9, y: 0, width: 1.8, length: 0.6 },
    { id: 'p3', item: 'desk', label: 'Desk', x: 0, y: 2.7, width: 1.2, length: 0.6 },
    { id: 'p4', item: 'nightstand', label: '', x: 3.95, y: 0.5, width: 0.45, length: 0.4 },
  ],
}

const STEPS_COPY = [
  { icon: Camera, title: 'Photograph your room', text: 'Capture a few overlapping views with your camera, or upload photos you already have.' },
  { icon: Compass, title: 'Confirm directions', text: 'Tell us which way photo 1 faces. We never guess true north from pixels.' },
  { icon: LayoutDashboard, title: 'Review the floor plan', text: 'Check and correct the plan and furniture, then see it evaluated against traditional Vastu guidance.' },
  { icon: Sparkles, title: 'Preview a redesign', text: 'Get a proposed layout and a visualization built from the same design decisions.' },
]

export default function Landing() {
  const nav = useNavigate()
  const { project, reset } = useProject()
  const started = project.setup.name.trim().length > 0 || project.photos.length > 0
  const resume = STEPS[Math.max(0, furthestStep(project))] ?? STEPS[0]
  const begin = async () => { await reset(); nav('/project/setup') }
  return (
    <>
      <Header showReset={false} />
      <main>
        <section className="hero">
          <div className="hero-copy fade-in">
            <div className="eyebrow">Room analysis · Vastu · Redesign</div>
            <h1>Understand your room.<br />Then reimagine it.</h1>
            <p className="lead">Photograph a room, confirm which way it faces, and see how its layout reads against traditional Vastu guidance — then preview a thoughtfully rearranged version built from the same plan.</p>
            <div className="row">
              <Button variant="sage" size="lg" icon={<ArrowRight size={18} />} onClick={begin}>Start New Room Analysis</Button>
              {started && <Button variant="ghost" size="lg" onClick={() => nav(resume.path)}>Continue “{project.setup.name || 'your room'}”</Button>}
            </div>
            <p className="tiny muted" style={{ marginTop: '1rem' }}>Vastu is presented as a traditional design framework — not a scientific standard. Every rule is shown with its reasoning, and you stay in control of every measurement.</p>
          </div>
          <figure className="hero-art" aria-hidden="true">
            <FloorPlan {...ILLUSTRATION} />
            <figcaption className="tiny muted">Illustration — not a result</figcaption>
          </figure>
        </section>

        <section className="band">
          <div className="inner">
            <div className="eyebrow">How it works</div>
            <h2>Four calm steps from photographs to a plan</h2>
            <div className="grid cols-4 how">
              {STEPS_COPY.map(({ icon: Icon, title, text }, i) => (
                <div className="how-item" key={title}><span className="how-n">{i + 1}</span><Icon size={22} strokeWidth={1.6} /><h4>{title}</h4><p>{text}</p></div>
              ))}
            </div>
          </div>
        </section>

        <section className="inner honest">
          <div>
            <h3>What’s automatic, and what’s yours</h3>
            <p>Object detection and (when available) photo-based geometry give you a starting point. Photo geometry is approximate and has no real-world scale, so measurements you enter are always used first and estimates are always labelled. Compass directions come only from the orientation you confirm.</p>
          </div>
          <ul className="checks">
            <li>Estimated vs. measured values are always distinguished</li>
            <li>Floor plan, Vastu check and redesign share one editable layout</li>
            <li>Redesign images are clearly labelled as AI proposals</li>
          </ul>
        </section>
      </main>
      <footer className="site-footer"><div className="inner small muted">Vastu Atelier · Capstone project · Generated images are visual proposals and may not preserve exact geometry.</div></footer>
    </>
  )
}
