# Vastu Atelier — room analysis, Vastu check & AI redesign

A full-stack capstone application: photograph a room → confirm which way it faces → review the current floor plan →
see it evaluated against a configurable set of traditional Vastu rules → get a redesigned layout **and** an AI room
visualization generated from the *same* structured design spec.

* **Backend** — FastAPI (`main.py`, `app/`), YOLO detection, VGGT geometry, Vastu rules engine, redesign planner,
  pluggable image-generation providers.
* **Frontend** — React 19 + Vite + React Router (`frontend/`), SVG floor-plan editor, camera/upload capture, wizard flow.

> **Read "Verification status" below before presenting this.** Several pieces (real VGGT inference, real YOLO inference,
> real image-provider calls) could not be run in the environment where this was built; they are implemented, unit-tested
> against stubs/mocks, and clearly labelled — but they have not been exercised end-to-end with real weights or API keys.

---

## 1. What was wrong, and what changed

### The two issues you reported

**Floor-plan direction labels.** I reproduced this against your original `floorplan.py` by rendering all four orientations.
The edge *text* was already correct (your `top = EAST` example gave right = SOUTH, bottom = WEST, left = NORTH).
The real defects were:

| # | Defect | Fix |
|---|--------|-----|
| 1 | **The north arrow pointed the wrong way in all four orientations** (it pointed *toward the room*, not at the NORTH edge). | Replaced by a compass rose whose N arrow rotates to the edge facing north. |
| 2 | Arrow label collided with the dimension text (`top=east`, `top=south`). | Re-laid out labels/dimensions with separate offsets. |
| 3 | Direction logic was implemented **three separate times** (`floorplan.py`, `vastu_engine.py`, `main.py`). | One module, `app/orientation.py`, used by everything; JS mirror in `frontend/src/lib/orientation.js`. |
| 4 | The parameter `north_direction` actually meant *"compass direction of the top edge"* — the opposite of what the name suggests. | Canonical name is now `top_edge_direction`; `north_direction` still works as a deprecated alias. |
| 5 | The user-confirmed orientation never drove the plan; a separate unrelated field did. | Orientation is resolved once (`facing_direction` + `facing_edge` → `top_edge_direction`); contradictory inputs are rejected (HTTP 422), never silently resolved. |

**Frontend ↔ backend workflow.** There was no frontend and VGGT was not connected to the API at all (it existed only as the
standalone script `vggt/run_vggt.py`). The whole workflow is now implemented and connected.

### Things in your brief that did not match the ZIP

* **Duplicate `RoomLayoutRequest` / `/room-layout/analyze`:** not present in the `main.py` I received (one of each). I kept a
  single definition and added a test that fails if a route is ever defined twice.
* **`POST /floorplan`:** it was `GET /floorplan`. Both exist now (`POST` renders a structured layout).
* **`/analyze-room` is YOLO only** — as you said — and returns `geometry_status: "not_reconstructed"`. That honesty is preserved.
* `vggt/run_vggt.py` reads `vggt/inputs/room_images`, but your photos are in `inputs/room-images`, and `vggt/outputs/` is empty,
  so that script had never produced output in this ZIP. I left it untouched; the API integration does not use it.

Your original files are kept in `legacy/` for diffing. The original request/response contracts are preserved (I replayed the
exact request behind your shipped `response.json` as a regression test).

---

## 2. Quick start

### Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt            # API + YOLO (pulls in torch)
cp .env.example .env                       # then edit (see §4)
python -m uvicorn main:app --reload --port 8000
# API docs: http://localhost:8000/docs      capability report: http://localhost:8000/health
```

The API **starts even if `ultralytics`/`torch` are missing**; `/health` then reports exactly what is unavailable and why.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local                 # VITE_API_BASE_URL=http://localhost:8000
npm run dev                                # http://localhost:5173
npm run build && npm run preview           # production build
```

`VITE_API_BASE_URL` is the only backend setting. If it is unset the app uses *the same host as the page, port 8000*
(handy for phones on your LAN). No machine-specific addresses are hard-coded.

### Using it from a phone

* Start the backend with `--host 0.0.0.0` and the frontend with `npm run dev` (it already listens on all interfaces).
* Open `http://<your-computer-LAN-IP>:5173`; set `VITE_API_BASE_URL=http://<LAN-IP>:8000`. CORS already allows private LAN origins.
* **Browsers only allow the live camera and compass sensors on HTTPS or `localhost`.** Over plain-HTTP LAN you still get
  *"Take a photo with phone camera"* (native camera app) and uploads. For the live camera/compass on a phone, serve over HTTPS
  (e.g. a tunnel such as `cloudflared`/`ngrok`, or a local HTTPS dev certificate).

---

## 3. Folder structure

```
main.py                    FastAPI app: original endpoints (contracts preserved) + routers
floorplan.py               Server-side PNG/PDF renderer (orientation-aware, doors/windows)
vastu_engine.py            Legacy 4-direction API (delegates direction logic to app/orientation.py)
app/
  orientation.py           ★ single source of truth for edge<->compass mapping, zones, orientation resolution
  schemas.py               Pydantic models (RoomLayout, Opening, FurniturePlacement, redesign requests…)
  vastu_rules.py           Data-driven rules engine (8 zones + centre; satisfied/violated/indeterminate)
  redesign.py              Constraint-based layout planner + structured redesign spec + prompt builder
  geometry.py              Numpy-only geometry from VGGT-style output (floor plane, footprint, scale, localisation)
  vggt_service.py          Lazy VGGT inference wrapper (torch imported only when used)
  room_analyzer.py         YOLO detection (lazy import) + furniture-candidate aggregation
  pipeline.py, jobs.py     Background job pipeline with REAL per-stage status
  image_providers.py       OpenAI + Gemini providers behind one interface; explicit errors, no fake output
  ingest.py, config.py, storage.py, furniture.py, routers/
config/vastu_rules.example.json   Example rule overrides (disable / change / add rules)
shared/orientation-cases.json     Hand-written ground truth shared by the Python and JS test suites
tests/                     pytest suite (160 tests)
frontend/                  React + Vite app (vitest suite, 92 tests)
e2e/                       Optional headless-Chrome end-to-end scripts
legacy/                    Your original main.py / floorplan.py / vastu_engine.py / room_analyzer.py
vggt/, yolov8n.pt, …       Your existing assets — untouched
```

---

## 4. Configuration (backend `.env`)

| Variable | Purpose |
|---|---|
| `IMAGE_PROVIDER` | `auto` (default; OpenAI if its key is set, else Gemini), `openai`, `gemini`, or `none` |
| `OPENAI_API_KEY`, `OPENAI_IMAGE_MODEL` (default `gpt-image-1.5`), `OPENAI_IMAGE_QUALITY` | OpenAI image generation/editing |
| `GEMINI_API_KEY`, `GEMINI_IMAGE_MODEL` (default `gemini-2.5-flash-image`) | Gemini image generation (free tier available) |
| `VGGT_ENABLED` | `auto` (default), `false` to disable |
| `VGGT_WEIGHTS_PATH` | local `model.pt`/`.safetensors` for offline use (otherwise downloaded from Hugging Face on first run, ~5 GB) |
| `VGGT_DEVICE`, `VGGT_MAX_IMAGES` | `auto`/`cpu`/`cuda`; photo cap for reconstruction (photo 1 is always kept) |
| `CORS_ORIGINS` | extra allowed origins (localhost / LAN ranges are allowed by default) |
| `MAX_IMAGE_BYTES`, `MAX_ROOM_IMAGES` | upload limits (10 MB, 12 photos) |
| `VASTU_RULES_FILE` | JSON file that disables/overrides/adds Vastu rules (see `config/vastu_rules.example.json`) |

**API keys live only in the backend environment.** The frontend never sees them.

### Enabling VGGT
`pip install torch torchvision` (CUDA build if you have a GPU), `pip install huggingface_hub safetensors einops`, keep the
`vggt/` clone where it is. `/health` → `capabilities.geometry_reconstruction` tells you whether it is ready. On CPU expect
minutes per run and several GB of RAM; use `VGGT_MAX_IMAGES` to bound it.

### Configuring the AI visualization
Set `OPENAI_API_KEY` (or `GEMINI_API_KEY`) in `.env` and restart. Without a key the app shows an explicit
*"Image generation isn't configured"* message with these instructions and still delivers the redesigned floor plan.
It never substitutes a placeholder image.

---

## 5. How the orientation model works

* The floor plan is a bird's-eye view: x right, y up. **`top_edge_direction`** is the compass direction of the drawing's *top* edge.
  Clockwise around the room the directions advance in order, so `top = east` ⇒ right = south, bottom = west, **left = north**.
* **The top of the plan is the wall photo 1 faces.** The user confirms which compass direction photo 1 faces (optionally cross-checked
  with the phone compass); that *is* `top_edge_direction`. True north is never inferred from pixels.
* Everything derives from `app/orientation.py` (and its JS mirror): edge labels, the compass-rose arrow, Vastu zones
  (3×3 grid → 8 directions + centre), door/window zones, bed-head and facing directions, redesign scoring, and the exported images.
* Changing the direction on the floor-plan page relabels the plan and re-evaluates every zone; furniture positions don't move.

---

## 6. API summary

| Method & path | Notes |
|---|---|
| `GET /health` | honest capability report (YOLO / VGGT / image generation) |
| `POST /analyze-room`, `POST /analyze-room-multiple` | original YOLO endpoints (multi also returns `furniture_candidates`) |
| `GET /floorplan` / `POST /floorplan` | PNG/PDF from query params / from a structured layout |
| `GET /vastu/rules`, `POST /vastu/analyze` | legacy `{room_type, placements}` **or** `{layout}` → full report |
| `POST /room-layout/analyze` | original contract + `orientation`, `vastu_report`, doors/windows |
| `POST /room-analysis/jobs` → `GET /jobs/{id}` | photos + context → VGGT/YOLO/geometry; poll for real stage status |
| `POST /redesign/plan` | proposed layout + Vastu before/after + budget + design spec |
| `GET /redesign/{id}`, `/redesign/{id}/floorplan?which=proposed\|current&format=png\|pdf` | retrieval / rendering |
| `POST /redesign/{id}/visualize` → job, `GET /redesign/{id}/visualization.png` | AI image from the same spec |

Errors from new endpoints use `{"detail": {"code", "message", "hint"}}` (e.g. `image_provider_not_configured`, `orientation_conflict`, `detection_unavailable`).
Jobs are kept **in memory** (lost on restart; clients get a 404 and can resubmit).

---

## 7. Verification status (what was actually run)

**Run and passing**
* `pytest` — **160 tests**: orientation mapping for all four cardinal directions (+ shared fixtures), geometry on a synthetic ray-cast
  room, Vastu engine, redesign planner properties (no overlap, door swing clear, in-room, all four orientations), API contracts incl.
  your original request replayed, upload validation, CORS, job pipeline (with stubbed models), provider request/response handling
  (mock transport).
* `vitest` — **92 tests**: the JS orientation module against the *same* fixture file, the rendered SVG's four edge labels and north-arrow
  rotation for every orientation, numeric-input regression, layout helpers.
* **Live end-to-end in headless Chrome against the running backend** (desktop *and* a 390 px phone viewport): setup → upload your
  `myroom*.jpeg` photos → orientation → furniture → analysis job → floor-plan editing (decimal entry, drag, arrow keys) →
  correcting directions through all four orientations → Vastu → redesign → results → reload persistence; plus the live camera
  (Chrome's fake camera device) and the permission-denied path. No horizontal overflow at 390 px on any step.
* Production `vite build`.

**Implemented but NOT verified with the real thing** (not possible in the build environment: no GPU, ~7 GB disk, no Hugging Face access, no API keys)
* **Real VGGT inference.** The wrapper follows the official `load_and_preprocess_images → model → pose_encoding_to_extri_intri →
  unproject_depth_map_to_point_map` flow, but was never run with weights. The geometry code (`app/geometry.py`) was validated only on
  a *synthetic* room: footprint recovered within ~1%, per-view furniture-centre errors 0.06–1.13 m (median ≈ 0.5 m). **Real-photo
  accuracy is unknown.** Treat reconstructed outlines/positions as editable estimates (the UI labels them so).
* **Real YOLO inference** in the build sandbox (ultralytics/torch could not be installed there). The detection call itself is the code from
  your original project; the surrounding changes were tested with stubs.
* **Real OpenAI/Gemini calls.** OpenAI's request shape was checked against its public API reference; Gemini's is written from the public
  `generateContent` docs and is the less certain of the two. Both are tested only via a mock HTTP transport.
* Phone compass, HTTPS camera on a real device, and any browser other than headless Chrome.

---

## 8. Known limitations

* VGGT output is non-metric. Real dimensions come from the user; without them a 1.4 m camera-height assumption yields rough estimates, always labelled.
* Photos rarely cover every wall; reconstruction is described everywhere as a *partial estimate* and reports perimeter coverage/confidence.
  Doors and windows are not detected — they are added by the user.
* YOLO's COCO classes cover bed, sofa, chair, dining table, TV, fridge, sink, oven (loose match for a stove) and plants — not wardrobes, desks, doors or windows.
* Directions are snapped to the four cardinal directions; rooms rotated away from the compass axes are approximated. Zones use the furniture centre on a 3×3 grid.
* Vastu rules encode commonly cited guidance, are configurable, show their reasoning and level of agreement, and make no scientific claim.
  Indeterminate rules (missing headboard/facing/openings) are reported as such, never guessed.
* The redesign planner is a deterministic heuristic (greedy, scored by the same rules), not a global optimiser; small rooms may report items it cannot fit.
  Budget figures are indicative placeholder ranges for *new/replaced items only*, not quotes.
* Generated images follow the layout only approximately and may not preserve exact geometry; they are labelled as AI proposals.
* Jobs and redesign specs: jobs in memory; specs/visualizations on disk under `data/`. The browser keeps the project in `localStorage` + IndexedDB (photos).
* PDF "report" is the browser's *Print / Save as PDF* of the results page; server-side PDF export covers floor plans only.

---

## 9. Tests

```bash
pip install -r requirements-dev.txt && python -m pytest tests -q          # backend
cd frontend && npm test                                                    # frontend
# optional browser e2e (backend on :8000, `npm run build && npm run preview` on :5173)
cd e2e && npm install && npm run e2e && npm run e2e:mobile && npm run camera
```
