# Handoff — AutoTrade Replacement

## Status saat berhenti

- Tanggal checkpoint: 2026-08-24 malam, Asia/Jakarta.
- Branch lokal: `kiro/dryrun-activation-dashboard`.
- Commit lokal terakhir: `de49a1d` (`fix: classify pair loss streak decisions`), belum push/deploy.
- VM masih pada `cdcb9a4`; service aktif, `NRestarts=0`, mode DRY RUN.
- Case file aktif: `investigations/in-out-trade-decision-stability-investigation.md`.
- Targeted controls: 132 test + 22 subtest lulus; satu Redis deprecation warning.

## Keputusan user

AutoTrade lama akan dirombak total karena secara de facto belum menunjukkan performa yang baik. Sasaran bukan “akurasi” nominal, melainkan net expectancy positif out-of-sample setelah fee, spread, slippage, dan latency, dengan accounting serta lifecycle deterministik.

## Temuan yang harus dibawa ke desain baru

1. PriceMonitor protective exit hanya menutup legacy ledger; normalized positions tetap OPEN.
2. ACE, BICO, dan HUMANITY terbukti sudah exit legacy tetapi menjadi ghost positions canonical.
3. Ghost positions memengaruhi equity, drawdown, dan keputusan entry portfolio.
4. Display/persistence dan execution entry tidak memakai satu canonical decision karena `pre_sr_recommendation` override.
5. State trailing, partial TP, time-stop, dan high-water mark masih ephemeral.
6. Pending-order worker gagal pada `sqlite3.Row.get`; stale pending orders tetap ada.
7. Snapshot fitur/gate per scan belum cukup untuk mengukur flip-rate atau replay keputusan.

## Prinsip replacement yang sudah disepakati

- Satu canonical decision untuk display, persistence, replay, dan execution.
- Satu canonical ledger dengan atomic, idempotent lifecycle.
- Entry/exit policy pure dan deterministic terhadap versioned snapshot.
- Persist seluruh exit-policy state dan parameter entry-time.
- Satu freshness/executable-price contract.
- Online calibration, explicit regime/change detection, dan hysteresis/no-trade bands dievaluasi sebagai kandidat—bukan diasumsikan otomatis unggul.
- Simulator yang sama untuk replay dan live dry-run.
- Promotion hanya melalui walk-forward out-of-sample evidence setelah biaya.
- Real trading tetap nonaktif sampai promotion gates terpenuhi dan user memberi persetujuan eksplisit.

## Titik lanjut besok pagi

Workflow aktif: `bmad-prd` Create, Fast Path. Belum ada PRD workspace karena langkah berikutnya adalah meminta brain dump user mengenai:

- perilaku entry ideal;
- lifecycle posisi dan exit ideal;
- target performa dan batas risiko;
- universe pair dan timeframe;
- kebutuhan operator/dashboard;
- tujuan akhir penggunaan uang asli;
- gagasan lama yang wajib dipertahankan atau dibuang.

Sesudah brain dump: buat PRD replacement → reviewer gate → epics → architecture → migration plan → implementation readiness.
