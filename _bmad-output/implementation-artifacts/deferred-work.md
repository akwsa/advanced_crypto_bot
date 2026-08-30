# Deferred Work

- source_spec: `spec-2-2-market-snapshot-eligibility-remediation.md`
  summary: Tetapkan fee rounding policy simulator berdasarkan exact walked notional, bukan rounded WAP.
  evidence: Review Story 2.2 menemukan ASK-ceil/BID-floor WAP dapat menggeser fee; ini merupakan kebijakan Story 2.3 yang tidak termasuk izin arithmetic quantity terbatas.

- source_spec: `spec-2-2-market-snapshot-eligibility-remediation.md`
  summary: Wiring orchestration wajib mengevaluasi InstrumentEligibility sebelum memanggil simulator.
  evidence: Simulator domain tetap dapat menerima snapshot stale, over-spread, non-member, atau systemic-failed jika caller melewati eligibility; integrasi runtime belum termasuk scope pure-domain Story 2.2.
