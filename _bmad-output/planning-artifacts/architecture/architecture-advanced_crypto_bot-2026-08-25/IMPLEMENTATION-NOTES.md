# Implementation Notes — AutoTrade Replacement

Dokumen ini menerjemahkan Architecture Spine menjadi urutan implementasi dan batas evaluasi. Ketentuan normatif tetap berada di `ARCHITECTURE-SPINE.md` dan PRD; rationale, confidence, serta sumber primer berada di technical research.

## Decision and Assumption Register

| Status | Item | Consequence |
| --- | --- | --- |
| `[ADOPTED]` | Universe mencakup seluruh spot-IDR yang lolos dynamic eligibility | Membership point-in-time dan mempunyai exclusion reason; bukan daftar pair statis. |
| `[ADOPTED]` | Horizon swing intraday sampai multi-day | Candidate, Position, policy, evidence, dan report selalu membawa `horizon_id`; satu pair tidak boleh mempunyai Position lintas Horizon secara bersamaan pada MVP. |
| `[ADOPTED]` | Maksimum satu Position 10% equity | Ini limit notional, bukan target return. Liquidity, correlation, stop distance, volatility, cost, dan uncertainty hanya dapat mengecilkannya. |
| `[ADOPTED]` | Hard portfolio drawdown trigger 10% | Breach menutup entry, membatalkan working entry, dan memulai risk reduction menuju zero exposure; slippage dapat membuat realized loss melewati trigger. |
| `[ADOPTED]` | Legacy boleh menjadi Champion jika terbukti | Legacy terlebih dahulu wajib menggunakan snapshot, decision, Fill lifecycle, Policy State, simulator, dan evidence gate yang sama. |
| `[ADOPTED]` | DRY RUN adalah boundary fisik | Runtime MVP tidak mempunyai live submit adapter atau trade-capable credential. |
| `[ASSUMPTION]` | CPython 3.12 line cukup untuk MVP | Image dipin ke 3.12.14; upgrade feature line dinilai terpisah agar tidak menambah migration risk. |
| `[ASSUMPTION]` | SQLite single-host cukup | Harus dibuktikan dengan load, busy, crash, disk-full, backup/restore, dan replay tests; initial qualified runtime adalah SQLite 3.53.4 exact allowlist. |
| `[ASSUMPTION]` | Risk-increasing entry turnover 40% equity per rolling 24 jam dan daily session Asia/Jakarta | Telemetry dapat mengubahnya melalui approved policy version; protective exit tidak pernah diblokir turnover. |
| `[ASSUMPTION]` | Redis hanya optional acceleration | Redis kosong atau down tidak boleh mengubah Decision maupun menghalangi recovery dari SQLite. |
| `[ASSUMPTION]` | Indodax menyediakan market evidence cukup | Adapter harus membuktikan cursor capability, continuity, depth, receive time, metadata, dan recovery; local cursor bukan bukti venue-gap freedom. |
| `[ASSUMPTION]` | Initial freshness, timeout, confirmation, and SLO baselines sesuai kondisi nyata | Baseline tetap fail-closed dan mengikat sampai telemetry plus versioned approval menggantinya. |
| `[DEFERRED]` | Live execution, auto-promotion, auto-retraining, deep/RL-first, dan unrestricted Kelly | Tidak masuk MVP dan tidak boleh tersembunyi sebagai config toggle. |

## Truth and Evidence Foundations

Fondasi berikut membuat outcome dapat dipercaya. Mereka dapat menurunkan reported performance karena menghapus fills optimistis dan P&L ganda; itu koreksi kebenaran, bukan penurunan kualitas system.

| Priority | Foundation | Material effect | Architecture consequence |
| --- | --- | --- | --- |
| P0 | One canonical Decision and Fill-based accounting | Menghilangkan perbedaan In Trade/Out Trade, action overwrite, ghost Position, dan P&L dari ledger yang bertentangan. | AD-03–AD-07, AD-12; prerequisite untuk menilai strategi apa pun. |
| P0 | Cost-aware no-trade | Gross edge kecil sering hilang setelah implementation shortfall; trade lemah harus ditolak sebelum Intent. | Strategy menghasilkan proposal/gross evidence; `CostModelPort` menghasilkan size-specific shortfall distribution; `DecisionService` membentuk conservative net edge menurut AD-09–AD-10. |
| P0 | Point-in-time universe, L2, and capacity | Menghapus survivorship bias, candle-price fills, serta order yang tidak executable pada target size. | AD-08, AD-13–AD-15, AD-24; eligibility, price, target size, cursor quality, dan evidence dibekukan bersama snapshot. |
| P0 | Fill-aware simulator plus TCA | Mengubah evaluasi dari signal accuracy menjadi executable outcome dan mengungkap partial/non-fill, latency, rejection, serta shortfall. | AD-12–AD-16; historical replay dan live DRY RUN memakai lifecycle/cost model yang sama. |
| P0 | Leakage-safe evidence and complete trial ledger | Mencegah selection bias, repeated trials tersembunyi, dan benchmark yang diganti setelah hasil terlihat. | AD-14–AD-15; purge/embargo dari maximum overlap, full trial family, DSR plus PBO, frozen holdout, dan forward shadow. |
| P0 | Deterministic portfolio allocation | Mencegah hasil bergantung urutan pair dan memastikan seluruh candidate memakai equity, liquidity, correlation, dan cutoff yang sama. | AD-11 dan AD-24; seluruh loser arbitration tetap memperoleh Canonical Decision dan structured reason. |

## Trading Hypotheses Worth Funding

Initial executable policy adalah `NoEntryChampion`. Tidak ada hipotesis di bawah yang memperoleh kewenangan trading sebelum seluruh evidence gate lulus.

| Priority | Hypothesis | Evidence-aware recommendation | Architecture boundary |
| --- | --- | --- | --- |
| P1 | Simple long/cash momentum | Bangun sebagai baseline Challenger yang mudah diaudit dan eligible for Champion; jangan menyalin parameter paper 2–4 minggu ke horizon intraday–multi-day. | Pure `StrategyPort`, costed local OOS, same opportunity set, final frozen holdout, dan forward shadow. |
| P1 | Nonlinear signed order flow | Global daily/weekly world-order-flow evidence memotivasi Challenger; nilai local signed flow untuk IDR/intraday belum terbukti. | Implementasi hanya setelah continuity, aggressor classification, point-in-time coverage, dan local net-cost OOS proof. |
| P1 | Regime-conditioned momentum | Perlakukan sebagai versioned `ResearchRegimeFeature`; transfer evidence UP→UP ke sub-week IDR masih medium–low. | Tidak bercampur dengan `SafetyChangeAlarm`; regime artifact, effective time, confidence, dwell, dan trial family dibekukan. |
| P1 | Calibrated uncertainty | Static/out-of-fold calibration plus proper-score/coverage monitoring wajib; adaptive/conformal calibration tetap Challenger dan tidak menjamin profit. | Missing/stale calibration: `ABSTAIN` ketika flat, no exposure increase ketika exposed; setiap online update menjadi `CalibrationUpdated` fact. |
| P1 | Downside/volatility/correlation allocation | Uji simple equal-risk/conservative scaling sebelum optimizer kompleks. Separation of authority kuat; optimizer uplift lokal belum pasti. | Hanya RiskGovernor/AllocationCycle yang menentukan target quantity dan tidak pernah melampaui hard envelope. |

## Evidence Confidence and Transfer Limits

| Finding | Confidence in source mechanism | Confidence for spot-IDR intraday–multi-day |
| --- | --- | --- |
| Cost-aware action gate | High | Medium for exact local threshold/cost distribution |
| Momentum anomaly | Medium–high | Medium after local all-in costs |
| World signed-order-flow predictability | Medium–high | Low–medium for local intraday flow |
| Regime change as safety control | High | Medium; regime as alpha is medium–low |
| Static calibration/coverage monitoring | High | Medium for economic uplift |
| Adaptive/conformal calibration | High for coverage method | Low–medium for PnL uplift |
| Portfolio/risk authority separation | High | High; optimizer-specific uplift is medium |
| 15-minute reversal rejection as default | Medium; very recent preprint | Medium pending venue-specific cost/fill proof |

## Methods Not Approved as Default

| Method | Disposition | Reason |
| --- | --- | --- |
| 15-minute mean reversion | Reject as default | Preprint 22 Agustus 2026 pada Binance melaporkan gross edge maksimum sekitar 1,3 bp versus benchmark round-trip sekitar 5 bp. Niche experiment baru legal bila venue-specific OOS fill/cost margin positif. |
| Triangular arbitrage | Scope rejection for MVP | Tidak sesuai single-venue swing focus dan memerlukan latency/fill simultaneity architecture berbeda; bukan klaim bahwa metode mustahil profit. |
| Deep learning or reinforcement-learning first | Reject for baseline | Menambah data, leakage, reproducibility, dan governance burden sebelum execution truth dapat dipercaya. |
| Indicator zoo or unrestricted ensemble search | Reject | Memperbesar multiple-testing family dan selection bias tanpa new-information thesis yang jelas. |
| Unrestricted Kelly sizing | Reject in production | Estimation error dan tail risk tidak kompatibel dengan hard envelope. Risk-constrained Kelly hanya boleh menjadi offline benchmark dan tetap tidak dapat melampaui hard limits. |
| Automatic retraining or promotion | Reject | Detector boleh meminta freeze/deactivation, tetapi tidak boleh mengubah model atau strategy authority sendiri. |

## Brownfield Disposition

| Existing area | Disposition | Required boundary |
| --- | --- | --- |
| `autotrade/contracts.py` | Reuse concepts/tests only | Pertahankan immutable/hash/idempotency lessons; jangan port `default=str`, binary float, implicit current time, atau local `fcntl`. Canonical serializer menolak unsupported types. |
| `autotrade/valuation.py` | Rewrite; reuse fail-closed semantics/fixtures only | Canonical equity memerlukan Decimal/fixed-point, executable L2 liquidation walk, fee/tax/exit cost, instrument scale, snapshot ID/time, serta conformance tests. |
| `autotrade/strategy2/state_machine.py` | Reuse state-machine lessons | Port ke pure domain state; tidak bergantung runtime callback atau shared mutable object. |
| `autotrade/strategy2/repository.py` and `core/database.py` | Reuse transaction test ideas only | Runtime DDL dan direct write dilarang; seluruh mutation masuk fenced unit of work dan offline schema migration. |
| `signals/signal_queue.py` | Transport seed only | Queue bukan source of truth; durable outbox, idempotent inbox/checkpoint, explicit ack, retry, dan dead-letter mengikuti AD-06. |
| Current dashboard | Reuse GET schema/static UI only | Retire direct canonical DB dan private venue calls; target Read API adalah process read-only/query-only tanpa trade-capable credential. |
| `api/indodax_api.py` | Do not reuse as target adapter | Public, private balance, legacy `/tapi`, serta create/cancel harus dipisah menjadi least-privilege ports; legacy fallback dilarang. |
| `scalper/`, `autohunter/`, and manual order handlers | Exclude from target artifact/process/DB | Brownfield live paths, termasuk `force_real_trading=True`, tidak boleh berbagi process, credential, DB, atau authority scope dengan DRY RUN replacement. |
| `bot.py`, runtime callbacks, PriceMonitor direct close, direct AutoTrade writes | Retire behind strangler | Tidak ada Decision overwrite, order submission, settlement, runtime DDL, atau DB mutation langsung sesudah cutover. |
| Local legacy `trades`, `pending_orders`, balance/position tables, Redis positions | Migrate then project/read-only | Import hanya fakta terbukti; ambiguity dikarantina; venue response tetap external evidence; projection dapat dibangun ulang dari journal. |
| Docker Python 3.11 and unlocked dependency ranges | Replace | Build mem-pin CPython 3.12.14, SQLite 3.53.4/source ID, dependency lock, image/base digest, schema, dan SBOM. |

## Build and Cutover Gates

1. Buat canonical types, explicit identifier mapping, serialization, state machines, and property tests sebelum adapter.
2. Implementasikan offline forward schema migration serta runtime exact-schema verification; runtime startup tidak menjalankan DDL.
3. Implementasikan SQLite journal/unit of work, CAS fencing, tamper-evident event chain, outbox/inbox, replay modes, invariants, and runtime PRAGMA/source-ID gates.
4. Implementasikan point-in-time market snapshot, dynamic eligibility, dan versioned venue-capability registry; validasi Public REST, Private REST, Trade API 2.0, Market Data WebSocket, dan Private WebSocket secara terpisah untuk cursor, gap/time/depth/metadata, recovery, serta larangan legacy fallback.
5. Implementasikan simulator dan OrderCoordinator dengan duplicate, out-of-order, partial Fill, cancel/fill race, timeout-after-acceptance, dan `UNKNOWN` corpus.
6. Implementasikan `NoEntryChampion`, simple baseline, dan legacy candidate melalui StrategyPort; semua non-null policy shadow dahulu.
7. Tambahkan CostModel, static calibration, explicit adaptive updates, AllocationCycle, Evidence Specification, full trial ledger, walk-forward, DSR/PBO, TCA, frozen holdout, dan forward shadow.
8. Jalankan fault suite pada boundary sebelum commit; sesudah commit/sebelum publish; sesudah publish/sebelum transport ack; sesudah consumer effect/checkpoint commit/sebelum ack; dan selama recovery. Injeksi venue ambiguity, duplicate/delayed/out-of-order Fill, WebSocket gap, Redis loss, `SQLITE_BUSY`, disk-full/I/O error, clock rollback, stale data, stale epoch, serta compound recovery failure. Setelah fault wajib lulus integrity, accounting conservation, no duplicate submit, fail-closed latch, eventual outbox disposition, dan deterministic restart.
9. Inventarisasi legacy facts; buat Online Backup di writer barrier; simpan encrypted off-host copy; restore terisolasi; classify ambiguity; append corrections; capai zero unexplained mismatch dan zero unresolved working `UNKNOWN`.
10. Lakukan stop-the-world portfolio-namespace cutover: stop/drain seluruh writer lama, record high-water, claim higher epoch, start exact target artifact, replay/projection check, lalu enable entry. Reverse cutover mengikuti prosedur sama dengan epoch lebih tinggi; legacy writer tidak diaktifkan lewat config rollback.
11. Terima MVP hanya jika safety invariants, SLO specification/observation, restore/replay, DRY RUN lifecycle, migration, and evidence gates lulus. Profitability dinilai terpisah dan tidak dapat menghapus integrity failure.

## Required Verification Artifacts

- Dependency-direction and forbidden-import contract test.
- Canonical schema fixtures, ID vectors, event-chain/checkpoint verification, dan versioned semantic projection/hash corpus.
- Property tests untuk cash, fee, quantity, Position, terminal Order, Policy State, allocation order-independence, dan risk conservation.
- Three-mode deterministic replay report dengan dua clean-run semantic hash identik dan zero external-call counter.
- Per-product Indodax capability registry dan contract tests, cursor-capability report, serta recorded gap/recovery corpus.
- Simulator-versus-observed TCA calibration report dengan `OBSERVED`, `INFERRED`, `SIMULATED`, dan `COUNTERFACTUAL` labels.
- Trial-ledger completeness, leakage checks, DSR/PBO, frozen holdout, forward shadow, and sealed Evidence Report.
- SQLite 3.53.4 version/source-ID/compile-option and PRAGMA startup gate; WAL concurrency/checkpoint-starvation, crash recovery, Online Backup, off-host checksum, and isolated restore report.
- Fault-boundary matrix dengan postcondition results, cutover/reverse-cutover rehearsal, legacy-writer absence proof, migration inventory, ambiguity disposition, reconciliation, dan event/outbox high-water mark.
- Operational SLO specification berisi numerator/denominator, threshold, window, exclusions, owner, alert/action, dan error-budget policy.
- Security assertion bahwa DRY RUN artifact tidak membawa live submission adapter, trade-capable credential, atau live subsystem dependency.

## Decision Evidence Register

| AD | Evidence type | Authority / reality check | Revalidation trigger |
| --- | --- | --- | --- |
| AD-01–AD-07, AD-12, AD-16–AD-18, AD-23, AD-26–AD-27 | Brownfield defect + architecture decision | `bot.py`, `core/database.py`, `autotrade/`, Redis queues, PRD incident/reconciliation inputs | Writer/submitter inventory berubah; new mutation path; schema/event revision |
| AD-08, AD-13, AD-29 | Official venue contract + unproven local capability | Indodax official API catalog and per-product docs; contract test required | Documentation commit, endpoint/channel, cursor, or rate-limit change |
| AD-09–AD-11, AD-15, AD-24–AD-25, AD-28 | Adopted product policy + research hypothesis | Final PRD and technical research; numerical baselines remain `[ASSUMPTION]` | Evidence window, risk-policy version, Horizon/retention approval, or telemetry breach |
| AD-14, AD-19, AD-21–AD-22 | Primary technical docs + build/drill proof required | Python, SQLite, Astral uv, Redis, backup/replay research | Tool/runtime security release, base digest, lock/schema change, or failed drill |
| AD-20 | Adopted safety boundary + negative artifact proof | PRD; current mixed live/DRY brownfield is migration risk, not conformance proof | Process/image/credential graph change |

Before implementation-readiness, generate a complete writer, order-submitter, credential, process, and canonical-file inventory. Every legacy path must be classified `remove`, `adapter`, `projection`, or `migration-only`; no unclassified mutator may survive cutover.

## Evidence Source

Rationale, literature limits, current-version checks, dan tautan sumber primer terdapat di [technical-impactful-modern-trading-architecture-research-2026-08-25.md](../../research/technical-impactful-modern-trading-architecture-research-2026-08-25.md).
