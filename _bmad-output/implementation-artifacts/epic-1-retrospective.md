# Retrospective Epic 1 — Keputusan yang Dapat Dibuktikan

Tanggal: 2026-09-11
Status: selesai

## Epic Review

Epic 1 menyelesaikan enam story dan membangun fondasi deterministik `autotrade_next`:

- `1.1`: encoding canonical `atr-json-v1` dan identity deterministik `<kind>:v1:<digest>` (SHA-256) untuk Candidate, Decision, Intent, Event, dan Client order.
- `1.2`: candidate snapshot point-in-time membekukan data, clock, universe, dan configuration sebelum gate pertama.
- `1.3`: setiap Candidate berakhir pada tepat satu Canonical Decision yang legal terhadap Position state.
- `1.4`: cost-aware abstention dan hysteresis mencegah overtrade dari gross signal, biaya, dan noise.
- `1.5`: deterministic decision replay dari clean store menghasilkan transition yang identik.
- `1.6`: provenance read-only menyajikan trail Candidate ke Decision tanpa membuka database canonical.

### What Worked

- Canonical bytes dan recipe identity immutable membuat replay menghasilkan ID yang sama pada retry/replay fakta yang sama.
- Contract tests menjadi executable specification: 46 test fondasi awal bertumbuh menjadi suite `tests/autotrade_next` 478/478 yang menjadi gate setiap story berikutnya.
- Dependency boundary (tanpa impor database/exchange/Telegram/runtime lama) menjaga domain tetap murni dan mudah diaudit.

### Challenges and Lessons

- Penolakan float dan `Decimal` memaksa presisi via `ScaledInteger`; konversi di boundary runtime harus eksplisit sejak awal desain.
- Determinisme timestamp (UTC mikrodetik tetap) mudah rusak oleh fixture wall-clock; dibuktikan lagi pada regression legacy saat Story 3.4.
- Identitas deterministik hanya berguna jika field projection terkunci; perubahan recipe wajib versi baru, bukan edit diam-diam.

## Next Epic Preparation

- Fondasi identity/replay ini menjadi prasyarat Epic 2 (execution) dan Epic 5 (cutover); jangan longgarkan canonical encoding saat integrasi runtime.
- Provenance read-only menyiapkan dashboard/integrity cockpit tanpa membuka jalur tulis dari presentation layer.

## Action Items

| Owner | Action | Priority |
|---|---|---|
| Developer | Jaga versioned identity recipe saat wiring runtime; perubahan preimage wajib versi baru. | High |
| Developer | Pertahankan boundary test dependency saat modul runtime baru ditambahkan. | Medium |

## Outcome

Epic 1 memenuhi acceptance criteria seluruh enam story. Platform remains DRY RUN-only and no live trading activation is implied by this retrospective.
