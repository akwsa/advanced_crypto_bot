# Retrospective Epic 4 — Evidence dan Promotion Tersegel

Tanggal: 2026-09-11
Status: selesai

## Epic Review

Epic 4 menyelesaikan enam story dan menegakkan pemilihan strategy berbasis evidence yang adil dan tersegel:

- `4.1`: Experiment dan opportunity universe dibekukan sebelum window dibuka; input tidak dapat diganti setelah outcome terlihat.
- `4.2`: Champion dan Challenger dinilai pada Candidate, cost, dan opportunity context yang sama tanpa authority tersembunyi.
- `4.3`: Trial dan matured outcome lengkap tersimpan termasuk kegagalan, mencegah selection bias.
- `4.4`: perbandingan leakage-safe dengan method terkunci melawan benchmark yang sama.
- `4.5`: Evidence Report immutable menggabungkan integrity, calibration, execution, risk, dan performance.
- `4.6`: promotion/demotion teraudit; performance tidak dapat mempromosikan dirinya sendiri.

### What Worked

- Pembekuan universe dan eligibility sebelum outcome menutup jalur multiple testing bias pada desain contract.
- Pemisahan experiment namespace sejalan dengan Strategy 2 (`strategy2_*`) yang benar-benar terisolasi dari kas dan posisi Strategy 1.
- Audit faktual 2026-08-30 yang menilai Epic 4 6/6 FAIL pada snapshot tersebut memaksa remediasi nyata; status `done` akhir terverifikasi lewat contract suite, bukan klaim.

### Challenges and Lessons

- Contract tanpa runtime tidak menghasilkan evidence nyata: pada snapshot audit, story ini "berupa contract minimal". Verdict jujur (FAIL) lebih berguna daripada status done palsu.
- Promotion gate hanya bermakna setelah ada trial data sungguhan; tanpa wiring runtime, sealed report tetap kosong secara substantif.
- Deflated Sharpe Ratio dan Probability of Backtest Overfitting disebut sebagai syarat promotion; implementasi metrik ini harus menyertai wiring runtime, bukan sesudahnya.

## Next Epic Preparation

- Kerangka experiment siap dipakai begitu runtime replacement ter-wire dan menghasilkan Candidate nyata.
- Keputusan promotion pertama harus menunggu trial matured dari DRY RUN; jangan promosi dari gross return atau jumlah trade saja (sesuai batas dokumen strategy).

## Action Items

| Owner | Action | Priority |
|---|---|---|
| Officer | Putuskan kriteria promotion numerik (DSR/PBO threshold) sebelum trial DRY RUN dimulai. | High |
| Developer | Sambungkan experiment registry ke runtime saat cutover agar sealed report terisi data nyata. | Medium |

## Outcome

Epic 4 memenuhi acceptance criteria seluruh enam story. Platform remains DRY RUN-only and no live trading activation is implied by this retrospective.
