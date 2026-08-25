## Document Summary

- **Purpose:** Menjadi kontrak produk normatif untuk replacement AutoTrade serta input langsung bagi architecture, epics, acceptance, dan keputusan Officer.
- **Audience:** Officer, PM/architect, dan implementation agents.
- **Reader type:** Humans; orientasi, glossary, journeys, dan ringkasan keputusan diperlakukan sebagai comprehension aids yang perlu dipertahankan.
- **Structure model:** Strategic/Context (Pyramid), dengan katalog FR sebagai reference layer di bawah ringkasan eksekutif.
- **Current length:** 4.289 kata pada dua dokumen, dengan 46 heading (41 di PRD, 5 di addendum). Distribusi H2 PRD: Tujuan 41; Visi 99; Target User 230; Glossary 300; Features 2.077; Constraints 166; NFR 173; Non-Goals 51; MVP Scope 230; Success Metrics 317; Risks 62; Confirmed Decisions 91; Open Questions 18; Assumptions 146. Addendum: pembuka 41; Decision Policy 58; Execution Evidence 36; Evaluation 34; Legacy Evidence 49.
- **Core question:** Apa yang harus dibangun, dibuktikan, dan dikendalikan agar AutoTrade replacement memiliki satu truth layer, risk envelope yang eksplisit, dan jalur promosi berbasis evidence?
- **Document-existence statement:** Dokumen ini ada untuk membantu Officer, PM/architect, dan implementation agents menyepakati outcome, scope, constraints, requirements, serta promotion gates replacement AutoTrade tanpa menafsirkan ulang keputusan produk.

## Structural Analysis

PRD memuat requirement yang kuat dan sebagian besar MECE, tetapi belum mengikuti pyramid secara optimal: keputusan final, scope, risk envelope, dan stage gates berada setelah katalog FR sepanjang 2.077 kata. Akibatnya Officer harus melewati detail replay, order recovery, market depth, dan evidence specification sebelum memperoleh ringkasan kontrak produk. Section Features juga menjalankan tiga fungsi sekaligus: katalog capability, acceptance contract, dan arahan arsitektur. Isi tersebut tetap relevan, tetapi perlu dilapis agar pembaca manusia dapat berhenti pada kedalaman yang sesuai.

Semua H2 melayani tujuan dokumen. Tidak ada bab yang layak dihapus sepenuhnya. Key User Journeys, Glossary, Brownfield Boundary, Confirmed Product Decisions, dan Assumptions Index merupakan comprehension/control aids yang penting dan harus dipertahankan. Redundansi nyata terutama terjadi pada risk limits, live-readiness boundary, canonical invariants, dan promotion evidence yang diulang di beberapa lokasi tanpa penunjuk source-of-truth.

## Recommendations

### 1. MOVE - Confirmed Product Decisions, MVP Scope, dan stage gates ke depan

**Rationale:** Setelah Visi, pembaca harus segera melihat keputusan normatif, batas MVP, dan definisi keberhasilan sebelum masuk ke katalog requirement; urutan yang disarankan adalah Visi → Confirmed Product Decisions → MVP Scope/stage gates → Target User/Journeys → Features.

**Impact:** ~0 kata; mengurangi waktu untuk menemukan keputusan paling kritis dan membuat struktur pyramid nyata.

### 2. MERGE - Tujuan Dokumen dan Visi menjadi Executive Contract

**Rationale:** Kedua bagian bersama-sama menjawab tujuan, outcome, operating mode, dan batas live-money, sehingga satu bagian pembuka 120–140 kata lebih cepat menetapkan konteks tanpa mengubah makna.

**Impact:** ~25 kata.

### 3. SPLIT - Features menjadi capability summaries dan acceptance contracts

**Rationale:** Pertahankan FR-1 sampai FR-34 di PRD, tetapi batasi badan utama tiap FR pada outcome normatif dan pindahkan paragraf state machine, precedence, tolerance, manifest fields, correction taxonomy, evidence estimator, serta failure corpus ke lampiran `Normative Acceptance Contracts`; ini bukan downgrade menjadi catatan non-normatif.

**Impact:** ~350 kata dari PRD utama (konten berpindah ke lampiran normatif, bukan dihapus); navigation membaik secara material.

**Comprehension note:** Lampiran wajib memiliki tautan dua arah dari setiap FR agar implementer tidak kehilangan acceptance detail.

### 4. MERGE - Satu Risk Envelope sebagai source of truth

**Rationale:** Angka 10% Position, 40% exposure, 2% daily loss, 0,5% risk-at-stop, dan 10% drawdown saat ini muncul pada FR-17/18, Promotion Gate, dan Confirmed Product Decisions; tetapkan satu tabel normatif `Risk Envelope` dan gunakan referensi dari bagian lain.

**Impact:** ~65 kata.

### 5. MERGE - Satu Stage and Authority Matrix untuk DRY RUN, Strategy-ready, dan Live-readiness

**Rationale:** Safety Guardrails, MVP Scope, MVP Exit Gates, Promotion Gate, Confirmed Decisions, dan beberapa FR mengulang batas kewenangan; satu matriks `Stage × allowed actions × required evidence × approver` akan menghilangkan ambiguitas sekaligus menjaga semua keputusan.

**Impact:** ~75 kata.

### 6. MOVE - Assumptions inline ke Decision/Assumption Register

**Rationale:** Marker `[ASSUMPTION]` tersebar di FR lalu diulang pada Assumptions Index; gunakan ID stabil (misalnya A-01), tampilkan marker singkat inline, dan simpan nilai, owner validasi, evidence yang diperlukan, serta titik keputusan hanya di register.

**Impact:** ~55 kata.

### 7. CONDENSE - Glossary menjadi tabel dan batasi pada istilah yang tidak didefinisikan oleh FR

**Rationale:** Glossary sangat berguna, tetapi 18 bullet panjang memperlambat scanning; tabel `Term | Normative meaning` mempertahankan definisi, sedangkan action legality tetap hanya di FR-2.

**Impact:** ~45 kata.

**Comprehension note:** Jangan menghapus Candidate Snapshot, Canonical Decision, Intent, Order, Fill, Position, Policy State, Experiment, Evidence Report, atau empat action; semuanya menopang mental model pembaca.

### 8. MERGE - Constraints, Cross-Cutting NFRs, dan minimum invariants dalam satu Quality & Safety Contract

**Rationale:** Ketiga elemen saat ini terpisah walaupun semuanya menetapkan kondisi lintas-fitur; kelompokkan sebagai Safety, Integrity/Determinism, Recovery, Security/Data Governance, Observability, dan Performance lalu tautkan invariant ke NFR yang membuktikannya.

**Impact:** ~50 kata.

### 9. MOVE - Legacy Evidence di addendum sebelum policy candidates

**Rationale:** Untuk alur manusia, masalah terbukti yang memicu replacement harus mendahului pilihan metode; urutan addendum yang lebih natural adalah Legacy Evidence → Decision Policy → Execution Evidence → Evaluation/Governance.

**Impact:** ~0 kata.

### 10. CONDENSE - Risks and Mitigations menjadi risk register yang dapat ditindaklanjuti

**Rationale:** Daftar sekarang ringkas tetapi tidak menunjukkan owner, trigger, atau requirement pengendali; tabel `Risk | Trigger | Mitigation/FR | Owner` memberi arsitektur dan epics jalur traceability tanpa menambah narasi.

**Impact:** biaya ~35 kata; nilai traceability lebih besar daripada penambahannya.

### 11. MERGE - Success Metrics dan Promotion Gate menjadi metric contract berlapis

**Rationale:** Pisahkan dengan tabel menjadi `Platform integrity`, `Strategy evidence`, dan `Counter-metrics`, lalu untuk setiap metric cantumkan measurement unit, pass boundary/assumption ID, dan evidence source sehingga gates tidak terlepas dari metrik.

**Impact:** ~30 kata.

### 12. PRESERVE - Key User Journeys dan Brownfield Boundary

**Rationale:** Journeys memberi pembaca manusia alur end-to-end, sedangkan Brownfield Boundary mencegah reuse komponen lama disalahartikan sebagai izin dual-write atau write authority.

**Impact:** 0 kata; jangan dipotong.

### 13. PRESERVE - Technical & Research Addendum sebagai dokumen terpisah

**Rationale:** Sumber primer dan kandidat metode mendukung keputusan tanpa membebani kontrak produk, sehingga pemisahan saat ini tepat; tambahkan hanya mapping `source → FR/assumption` agar provenance mudah ditelusuri.

**Impact:** biaya ~25 kata.

### 14. QUESTION - Tentukan status normatif addendum acceptance baru

**Rationale:** Pemindahan detail dari Features hanya aman jika tim menetapkan apakah lampiran acceptance merupakan bagian normatif PRD atau technical specification yang harus selesai sebelum architecture/epics; rekomendasi adalah lampiran normatif dengan version/status yang sama seperti PRD.

**Impact:** 0 kata; keputusan author diperlukan sebelum restrukturisasi.

## Proposed Top-Level Order

1. Executive Contract
2. Confirmed Product Decisions dan Risk Envelope
3. MVP Scope, Stage and Authority Matrix, serta Exit Gates
4. Target User dan Key User Journeys
5. Domain Model / Glossary
6. Functional Requirements per capability
7. Quality & Safety Contract (constraints, NFR, invariants)
8. Success / Promotion Metric Contract
9. Brownfield Migration Boundary
10. Risks, Assumptions, dan Open Questions
11. Normative Acceptance Contracts (appendix)
12. Technical & Research Addendum (separate supporting document)

## Summary

- **Total recommendations:** 14
- **Estimated reduction:** ~590 kata dari 4.289 kata (~14%) jika seluruh rekomendasi diterima; sekitar 350 kata merupakan relokasi ke lampiran normatif, sehingga pengurangan unik bersih sekitar 240 kata (~6%).
- **Meets length target:** Tidak ada target panjang yang diberikan.
- **Comprehension trade-offs:** Tidak ada keputusan normatif yang direkomendasikan untuk dihapus. Risiko utama adalah detail acceptance terlewat setelah dipindah; mitigasinya adalah status lampiran normatif, stable IDs, dan tautan dua arah.
