# Approval Gates Before Hermes Execution

> Semua gate di file ini wajib direview user sebelum Hermes Agent mulai coding. Dokumentasi ini berada hanya di lingkup `docs/dashboard-web/`.

---

## Gate 0 — Requirement Revision

**Approval update 2026-05-21:** User approved **Phase 1 read-only only** with scope:

- health,
- active pairs/chart,
- latest signals,
- trades/open positions,
- SSE stream.

All write/trading features remain deferred: SL/TP write, exact outbox writes, trade ticket persistence, DRY RUN trade intents, real trading, hunter control, and emergency stop are **not** included in this approval.

User perlu memutuskan:

- [x] Dashboard Phase 1 hanya read-only atau langsung termasuk SL/TP write? **Approved: Phase 1 read-only only.**
- [ ] Pair aktif diambil dari `watchlist`, config file, atau semua pair Indodax?
- [ ] Signal source: `data/signals.db`, `data/trading.db.signals`, atau gabungan?
- [ ] Dashboard akan diakses private/VPN atau public internet?
- [ ] Deployment pakai Docker Compose, PM2, atau hybrid?

Output gate:

```text
APPROVED_SCOPE = Phase 1 read-only only
APPROVED_PHASE_1_PANELS = health, active pairs/chart, latest signals, trades/open positions, SSE stream
DEFERRED_SCOPE = SL/TP write, signal outbox writes, trade ticket persistence, DRY RUN trade intents, real trading, hunter controls, emergency stop
```

---

## Gate 1 — Codebase Audit Final

Sebelum coding, Discovery Agent harus memperbarui:

- `../09-current-codebase-audit.md`
- `../architecture/data-source-contract.md`

Checklist:

- [ ] Runtime DB path final.
- [ ] Signal DB final.
- [ ] Redis key format final.
- [ ] Bot process manager final.
- [ ] Existing env vars final.

---

## Gate 2 — Security Approval

Checklist:

- [ ] Admin API key tidak akan masuk frontend bundle.
- [ ] Auth model dipilih: private basic auth / session cookie / JWT.
- [ ] Write endpoints disabled untuk Phase 1 read-only.
- [ ] Audit log wajib untuk Phase 1.5+.
- [ ] Dangerous controls ditunda atau disetujui eksplisit.

---

## Gate 3 — Migration Approval

Hanya berlaku untuk Phase 1.5+.

Checklist:

- [ ] Backup DB tersedia.
- [ ] Migration diuji di copy DB.
- [ ] Rollback SQL tersedia.
- [ ] Write hanya ke `dashboard_*` tables.
- [ ] Bot tetap aman jika table dashboard tidak ada.

---

## Gate 4 — Dangerous Controls Approval

Hanya untuk Phase 2.

Fitur yang termasuk dangerous controls:

- Dry Run ↔ Real Trading.
- Start/Stop Hunter.
- Emergency stop.
- Execute trade dari dashboard.

Minimum approval requirements:

- [ ] Confirmation phrase.
- [ ] Re-auth admin.
- [ ] Audit log.
- [ ] Cooldown.
- [ ] Bot-side safety validation.
- [ ] Manual rollback procedure.

