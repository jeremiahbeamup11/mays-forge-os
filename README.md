# Mays Forge OS

An operating system for cities. Mays Forge OS ingests municipal data, analyzes infrastructure inefficiencies, recommends sustainable solutions, and generates redevelopment blueprints for vacant and underutilized land.

Designed for small and mid-size cities that need enterprise-grade planning tools without enterprise budgets.

## Status

Early development. Target MVP customer: Peotone, IL (population ~4,200).

## Architecture

Monorepo containing:

- `backend/` — FastAPI + Python 3.12 + Supabase
- `frontend/` — Next.js 15 + TypeScript + Tailwind (not yet initialized)
- `docs/` — Architecture notes, design decisions, future roadmap

## The Four Pillars

1. **Ingest & Understand** — accept and contextualize city data (GIS, utility bills, photos, public datasets)
2. **Analyze & Predict** — detect infrastructure risks and inefficiencies in water, energy, and waste systems
3. **Optimize & Recommend** — propose prioritized, concrete interventions with projected savings
4. **Redevelopment Blueprints** — generate sustainable reuse concepts for vacant lots with metrics and cost estimates

## Development Setup

See `backend/README.md` (coming soon) for backend setup instructions.

## License

TBD
