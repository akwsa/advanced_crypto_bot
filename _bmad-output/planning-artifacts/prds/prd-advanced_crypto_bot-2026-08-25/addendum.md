# Addendum — AutoTrade Replacement

Addendum ini memuat detail teknis, opsi, dan sumber primer yang memengaruhi PRD, tetapi bukan merupakan requirement tingkat atas. Addendum ini bersifat supporting evidence; requirement dan Normative Acceptance Contract tetap berada di `prd.md` dengan stable FR ID.

## D. Legacy Evidence Driving Replacement

**Traceability:** Executive Contract, FR-2, FR-8–FR-11, FR-20, FR-28, dan FR-32–FR-34.

- Protective exits menutup legacy trades tetapi meninggalkan normalized positions OPEN.
- Entry execution dapat menghidupkan `pre_sr_recommendation` setelah final decision berubah.
- Exit Policy State dan stabilization context sebagian masih in-memory.
- Pending worker gagal pada `sqlite3.Row.get`.
- Decision snapshots belum cukup untuk menghitung flip-rate aktual.

Source case: `../../../implementation-artifacts/investigations/in-out-trade-decision-stability-investigation.md`.
## A. Decision Policy Candidates

**Traceability:** FR-4, FR-5, FR-21–FR-27, A-03, A-04, dan A-10.

- Online calibrated uncertainty: [AISTATS 2024](https://proceedings.mlr.press/v238/deshpande24a.html).
- Certificate-driven online calibration under shift: [UAI 2026](https://proceedings.mlr.press/v337/huang26b.html).
- Adaptive conformal inference: [Gibbs & Candès](https://arxiv.org/abs/2106.00170).
- Selection-conditional coverage: [CAP](https://arxiv.org/abs/2403.07728).
- Change-point detection: [NIST](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=911926).
- Transaction-cost no-trade region: [NBER 18709](https://www.nber.org/papers/w18709).

Candidate policy spine adalah: calibrated predictive distribution → net-cost utility → abstention/no-trade band → persisted state transition. Change detector adalah risk governor, bukan alpha source.

## B. Execution and Exchange Evidence

**Traceability:** FR-6–FR-20, NFR-1–NFR-8, A-01, A-02, A-05, dan A-06.

- [Indodax Public REST](https://github.com/btcid/indodax-official-api-docs/blob/master/Public-RestAPI.md)
- [Indodax Market Data WebSocket](https://github.com/btcid/indodax-official-api-docs/blob/master/Marketdata-websocket.md)
- [Indodax Private WebSocket](https://github.com/btcid/indodax-official-api-docs/blob/master/Private-websocket.md)
- [Indodax Trade API v2](https://github.com/btcid/indodax-official-api-docs/blob/master/INDODAX-TradeAPI-2.md)
- [Indodax Private REST](https://github.com/btcid/indodax-official-api-docs/blob/master/Private-RestAPI.md)
- [Indodax Deadman Switch](https://github.com/btcid/indodax-official-api-docs/blob/master/Deadman-switch.md)
- [FIA automated-trading controls](https://www.fia.org/sites/default/files/2024-07/FIA_WP_AUTOMATED%20TRADING%20RISK%20CONTROLS_FINAL_0.pdf)
- [Fill microstructure](https://doi.org/10.1016/S0304-405X(02)00134-7)
- [CloudEvents identity](https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md)

## C. Evaluation and Governance

**Traceability:** FR-22–FR-27, Success and Promotion Metric Contract, A-03, A-04, A-07, dan A-08.

- [Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
- [Deflated Sharpe Ratio](https://doi.org/10.2139/ssrn.2460551)
- [White Reality Check](https://onlinelibrary.wiley.com/doi/10.1111/1468-0262.00152)
- [Prequential evaluation](https://people.csail.mit.edu/jrennie/trg/papers/dawid-prequential-84.pdf)
- [NIST CUSUM](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm)
- [Federal Reserve SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm)

Numeric gates merupakan pre-registration proposals. DSR, PBO, dan calibration tidak membuktikan profit pada masa depan.
