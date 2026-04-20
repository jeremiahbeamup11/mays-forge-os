# Mays Forge OS — MVP Roadmap

Living document tracking progress from foundation to first demo with Bob Hennke (Peotone Public Works).

**Target:** End-to-end working MVP across all four pillars, demo-able to Bob on real Peotone data.

**Estimated total time:** 6–10 weeks at current pace.

---

## Phase 1 — Hardened Foundation ✅ COMPLETE

Production-grade backend skeleton before any features.

- [x] Monorepo structure (`backend/`, `frontend/`, `docs/`)
- [x] Git + GitHub + `.gitignore` covering Python, Node, secrets, OS junk
- [x] `uv`-managed Python 3.12 project with `pyproject.toml` + lockfile
- [x] FastAPI application with versioned `/api/v1` routing
- [x] Pydantic Settings v2 with `.env` loading and validation
- [x] Structlog structured logging (pretty in dev, JSON in prod)
- [x] Automatic secret redaction in logs
- [x] Request ID middleware with propagation and log correlation
- [x] Access log middleware with timing
- [x] Global exception handlers with consistent error shape
- [x] CORS configured for Next.js frontend
- [x] Health check endpoint
- [x] Pre-commit hooks: ruff, mypy (strict), pytest, file hygiene, private key detection
- [x] Pytest setup with async client fixture
- [x] 12 tests covering health, root, error handling, secret leaks
- [x] Makefile with `dev`, `test`, `lint`, `format`, `typecheck`, `check`, `clean`
- [x] README at monorepo root

---

## Phase 2 — Authentication & Database 🔜 NEXT

Supabase integration + JWT auth + Row-Level Security. Required before any user data flows through the system.

**Estimate:** 1–2 sessions.

- [ ] Create Supabase project (free tier)
- [ ] Populate real `.env` with Supabase URL + keys
- [ ] Supabase client wrapper in `backend/app/db/client.py`
- [ ] JWT verification utility in `backend/app/core/security.py`
- [ ] `get_current_user` FastAPI dependency in `backend/app/api/deps.py`
- [ ] First protected endpoint (`/api/v1/me` or similar)
- [ ] Initial database schema: `users`, `organizations`, `memberships`
- [ ] Row-Level Security policies on all tables
- [ ] Auth tests: no token → 401, bad token → 401, valid token → 200
- [ ] Document auth flow in `docs/AUTH.md`

---

## Phase 3 — Pillar 1: Ingest & Understand 🔜

Foundation of the OS. Every other pillar depends on this.

**Estimate:** 2–3 sessions.

- [ ] File upload endpoint with content type validation
- [ ] Size limits (per file + per request)
- [ ] Supabase Storage integration with per-org isolation
- [ ] CSV parser → structured data
- [ ] Image handler → Claude Vision analysis
- [ ] PDF text extraction
- [ ] Basic GIS file handling (GeoJSON first, then Shapefile)
- [ ] Claude-powered city context inference from ingested data
- [ ] Storage schema for parsed artifacts
- [ ] Ingest API tests (valid uploads, malformed files, oversized files, wrong types)
- [ ] Next.js frontend initialized in `frontend/`
- [ ] Frontend upload UI with progress + error states
- [ ] End-to-end test: upload CSV in browser → see parsed summary

---

## Phase 4 — Pillar 4: Redevelopment Blueprints 🔜

The differentiator. Demo-able to Bob.

**Estimate:** 2–3 sessions.

- [ ] Blueprint generation endpoint: lot photo + location → structured concept
- [ ] Claude Vision analysis of vacant lot images
- [ ] Structured prompt for sustainable use recommendations
- [ ] Rough sustainability metrics (water capture, energy, waste — rule-of-thumb for now)
- [ ] Ballpark cost estimation
- [ ] PDF report rendering (clean, professional)
- [ ] Report storage + retrieval
- [ ] Frontend blueprint viewer/downloader
- [ ] Tests for generation flow
- [ ] 🎯 **Milestone: show Bob the first blueprint**

---

## Phase 5 — Pillar 2: Analyze & Predict 🔜

Where the math libraries earn their place. Genuinely harder than prior phases.

**Estimate:** 3–5 sessions.

- [ ] Water infrastructure risk model (pipe age, material, pressure → leak probability)
- [ ] Energy waste detection (streetlight scheduling analysis)
- [ ] Stormwater overload simulation by zone
- [ ] Time-series forecasting for utility usage
- [ ] Prediction storage + versioning
- [ ] Dashboard visualizations (Recharts)
- [ ] Tests with synthetic data

---

## Phase 6 — Pillar 3: Optimize & Recommend 🔜

Builds on Phase 5. Given predicted risks, propose solutions.

**Estimate:** 2–3 sessions.

- [ ] Constraint optimization (PuLP) for infrastructure investment prioritization
- [ ] "What-if" simulation runner
- [ ] Recommendation ranking by ROI / impact / urgency
- [ ] Frontend: recommendation cards with drill-down
- [ ] Tests

---

## Phase 7 — Deployment 🔜

Get it running on real infrastructure.

**Estimate:** 1 session.

- [ ] Deploy backend to Render
- [ ] Deploy frontend to Vercel
- [ ] Production env vars configured on both platforms
- [ ] Real CORS origins locked to production domains
- [ ] UptimeRobot monitoring
- [ ] Smoke tests against live URLs
- [ ] Private link for Bob

---

## Phase 8 — Polish & Iteration 🔜

Real feedback from Bob. Real product decisions. Probably half of this phase will be things we don't predict.

---

## Future (Post-MVP) — Parked

Things that matter eventually but not now. Do not touch until MVP is live and Bob is using it.

- LangGraph / CrewAI agentic orchestration
- Llama fine-tuning
- PyTorch Geometric (graph neural nets)
- Qdrant (vs. PGVector which we'll use in MVP if needed)
- W&B experiment tracking
- TensorRT / ONNX / ROS 2 edge deployment
- Drones, towers, sensors — the hardware layer
- Multi-city support beyond Peotone

---

## Decision Log

Key choices and the reasoning. Append here when making architectural decisions.

- **2026-04-18** — Monorepo (not polyrepo) because solo founder, tight backend/frontend coupling.
- **2026-04-18** — `uv` instead of plain `pip` for speed + lockfile + `pyproject.toml` as source of truth.
- **2026-04-18** — Python 3.12 (not 3.14) for library ecosystem compatibility.
- **2026-04-18** — Pillar build order: Ingest → Blueprint → Analyze → Optimize. Ingest first because every other pillar depends on it; Blueprint second because it's the demo-able differentiator.
- **2026-04-18** — Strict mypy from day one. Paying the typing tax upfront to catch bugs before runtime.
- **2026-04-18** — Pytest on every commit via pre-commit. Will split fast/slow tiers when suite grows.
