# Retrospective Epic 2 — Executable DRY RUN Lifecycle

Tanggal: 2026-09-08
Status: selesai

## Epic Review

Epic 2 menyelesaikan tujuh story dari market evidence sampai calibration evidence:

- `2.1`: capability dan venue evidence Indodax dikualifikasi per product/channel dengan admission fail-closed.
- `2.2`: MarketSnapshot, executable depth, instrument eligibility, dan mixed-scale arithmetic dibakukan.
- `2.3`: simulator menyediakan satu lifecycle deterministic yang setara untuk DRY RUN.
- `2.4`: Intent, Order, Fill, cash, dan Position diselesaikan melalui fill-authoritative accounting.
- `2.5`: protective exit memiliki precedence tunggal, partial-fill protection, dan dust quarantine.
- `2.6`: recovery bersifat query-first, tidak mengevaluasi strategy baru, dan memakai correction evidence yang additive.
- `2.7`: calibration evidence memisahkan observed venue truth dari counterfactual/shadow evidence.

### What Worked

- Contract-first domain design membuat lifecycle dan evidence dapat diuji tanpa network atau credential.
- Satu schema simulator/venue mengurangi divergence antara DRY RUN dan jalur execution yang direncanakan.
- Recovery dan accounting diperlakukan sebagai invariant, bukan sekadar operational helper.
- Review loop memperbaiki masalah identity binding, mixed-scale arithmetic, UNKNOWN handling, dan persistence boundaries sebelum story ditutup.

### Challenges and Lessons

- Mixed numeric scales dan rounding harus ditangani sebelum arithmetic; pembulatan akhir tidak boleh mengubah evidence.
- UNKNOWN order state membutuhkan query-first recovery dan larangan resubmit otomatis sebelum venue evidence authoritative tersedia.
- Durable SQLite wiring, runtime allowlist, dan deployment evidence lintas story harus dicatat sebagai dependency eksplisit agar semantic contract tidak disalahartikan sebagai production readiness.
- Test corpus perlu mencakup product-specific authority; semantics endpoint tidak boleh diwariskan antar capability.

## Next Epic Preparation

- Pertahankan fill journal sebagai satu-satunya accounting authority.
- Gunakan evidence-bound identity dan deterministic replay untuk setiap extension lifecycle.
- Sertakan crash/restart, backup/restore, dan outbox recovery dalam release gate berikutnya.
- Jangan membuka live submission authority dari hasil simulator atau calibration evidence saja.

## Action Items

| Owner | Action | Priority |
|---|---|---|
| Developer | Keep venue/simulator schemas shared and contract-tested for future execution work. | High |
| QA | Add repeatable crash/restart and restore evidence to CI artifacts. | Medium |
| Officer | Approve any production runtime qualification separately from semantic story completion. | High |

## Outcome

Epic 2 selesai secara roadmap dan contract scope. DRY RUN tetap menjadi authority yang diizinkan; tidak ada klaim live execution readiness.
