# Retrospective Epic 3 — Fail-Closed Risk and Recovery Controls

Tanggal: 2026-09-08
Status: selesai

## Epic Review

Epic 3 menyelesaikan tujuh story untuk authority fencing, allocation, risk, safety, degradation, dan integrity cockpit:

- `3.1`: command authority dipagari writer epoch, token, sequence, dan lease invariants.
- `3.2`: exposure/reservation dialokasikan atomik dengan common-scale conservation.
- `3.3`: RiskGovernor memakai canonical equity, hard envelope, dan adjustment yang hanya mengurangi exposure.
- `3.4`: safety cause memakai scope lattice, severity/protective join, typed authority proof, dan additive clear history.
- `3.5`: kill switch dan hard drawdown memprioritaskan risk reduction menuju zero exposure.
- `3.6`: degradation dan delivery memisahkan entry freeze, shadow, safe latch, outbox, dan retry semantics.
- `3.7`: integrity cockpit serta audited recovery menyediakan read-only evidence dan recovery visibility.

### What Worked

- Fenced authority menjadi invariant lintas command, persistence, recovery, dan cutover.
- Risk-reducing protective actions tetap tersedia ketika entry dibekukan.
- Additive evidence dan typed reasons mencegah clear/promotion berdasarkan self-attested state.
- Adversarial review menemukan edge case yang bernilai tinggi: strict causal time, typed clear authority, forged history, dan public API exports.

### Challenges and Lessons

- Safety state bukan boolean; scope, severity, evidence, sequence, authority, dan causal time harus divalidasi bersama.
- Premature clear dan stale metadata sama-sama dapat membuka risiko; keduanya memerlukan proof yang terikat content dan sequence.
- Review workflow perlu dijalankan setelah full regression, karena regression legacy menemukan blocker di luar domain contract.
- Orchestration state harus direkonsiliasi setelah recovery manual agar status story, sprint, dan commit tidak divergen.

## Next Epic Preparation

- Jadikan safety cause lattice dan RiskGovernor boundary sebagai dependency wajib untuk fitur baru.
- Tambahkan invariant test untuk every new clear/recovery path sebelum implementation review.
- Pertahankan read-only cockpit; operator writes harus melalui authenticated command boundary.
- Bawa evidence retention dan rollback semantics ke setiap perubahan authority.

## Action Items

| Owner | Action | Priority |
|---|---|---|
| Developer | Add CI check for story/sprint/orchestration state consistency after workflow completion. | High |
| QA | Maintain no-premature-clear and protective-exit regression matrix. | High |
| Officer | Treat live-readiness as a separate approval and change proposal. | High |

## Outcome

Epic 3 selesai secara roadmap dan contract scope. Risk controls remain fail-closed, and completion does not authorize live trading.
