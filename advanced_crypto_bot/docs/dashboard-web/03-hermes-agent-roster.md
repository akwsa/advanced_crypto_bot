# 03 — Hermes/BMAD Agent Roster & AI API Keys

> File ini untuk perencanaan eksekusi Hermes/BMAD. Jangan menulis nilai API key. Implementasi dashboard utama tetap melalui approval gate.

---

## Prinsip Roster v1.2

Konfigurasi provider/model bisa berubah, jadi roster tidak boleh mengunci keputusan implementasi pada nama model yang mungkin outdated. Yang stabil adalah **skill BMAD/Hermes yang tersedia** dan peran tiap agent.

Provider/model aktual harus dicek saat eksekusi dengan konfigurasi Hermes saat itu. Dokumentasi hanya boleh menyebut nama env var jika perlu, bukan nilainya.

---

## Skill/Agent yang Dipakai

| Peran | Persona/Agent | Skill Hermes/BMAD | Fungsi |
|---|---|---|---|
| Orchestrator | Hermes Agent | `advanced-crypto-bot-development`, `test-driven-development` | Menjaga safety trading, TDD, test wrapper project |
| Architect | Winston | `bmad-agent-architect`, `bmad-create-architecture` | Finalisasi arsitektur, data contract, deploy diagram |
| PM | John | `bmad-agent-pm`, `bmad-create-prd` | PRD, scope MVP, prioritization matrix |
| UX | Sally | `bmad-agent-ux-designer`, `bmad-create-ux-design` | UX spec, stale/offline/error state, dashboard layout |
| Backend Dev | Amelia-style | `bmad-quick-dev`, `bmad-dev-story` | FastAPI read-only API, Redis/SQLite readers, tests |
| Frontend Dev | Alex-style | `bmad-quick-dev` | React dashboard, SSE client, panels, charts |
| QA/DevOps | Peter-style | `bmad-qa-generate-e2e-tests`, `bmad-check-implementation-readiness` | pytest/Playwright/smoke/deploy checklist |
| Review | Adversarial reviewers | `bmad-code-review`, `bmad-review-edge-case-hunter`, `requesting-code-review` | Security, edge cases, regression risk |

---

## Provider/API Key Handling

Env key names yang mungkin dipakai oleh Hermes tergantung config lokal:

- `TOKENROUTER_API_KEY`
- `SWIFTROUTER_API_KEY`
- `GEMINI_API_KEY`
- `FREEMODEL_API_KEY`

Rules:

- Jangan mencetak nilai key.
- Jangan menaruh key di frontend `.env` dengan prefix `VITE_*`.
- Jangan mengasumsikan Claude/DeepSeek/Qwen tersedia jika tidak dikonfirmasi di Hermes config runtime.
- Jika provider berubah, update dokumen ini tanpa mengubah arsitektur dashboard.

---

## Tugas Agent

### Winston — Architect

Deliverable:

- `architecture-dashboard.md`
- OpenAPI contract final Phase 1.
- SSE data contract.
- DB/Redis integration contract.
- SQLite busy/retry/cache strategy.
- Security model.
- Deployment diagram.

### John — Product Manager

Deliverable:

- PRD final.
- Prioritization matrix.
- MVP boundary 3–4 panel.
- Acceptance criteria.
- Launch readiness checklist.

### Sally — UX Designer

Deliverable:

- Wireframe desktop/mobile.
- Design system.
- Empty/stale/error/offline/unknown state design.
- Pair detail UX for Sprint 2.

### Amelia — Backend Developer

Deliverable:

- FastAPI scaffold.
- Read-only API.
- DB/Redis readers with fallback.
- SSE event stream.
- Heartbeat reader endpoint.
- Tests.

### Alex — Frontend Developer

Deliverable:

- React dashboard.
- Chart components.
- Health/pair/signals/trades panels.
- Native `EventSource` client.
- Freshness indicators.

### Peter — QA/DevOps

Deliverable:

- Test strategy.
- pytest + Playwright plan.
- Docker/Nginx or manual/PM2 deployment docs.
- Smoke test scripts.

---

## Human Approval Gates

Hermes Agent tidak boleh langsung implementasi dashboard utama sebelum user approve:

1. Final MVP scope.
2. Whether SL/TP write is included.
3. Whether dangerous controls are postponed.
4. Auth model.
5. Deployment target.

DB path/Redis audit awal sudah resolved untuk Phase 1, tapi tetap harus divalidasi ulang sebelum deploy produksi.
