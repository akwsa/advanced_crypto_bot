# Catatan Chat 2026-05-19

## Tujuan Hari Ini

Menyiapkan cara memakai Hermes/Pi dari WSL dan Termul untuk project:

```text
/home/officer/advanced_crypto_bot/advanced_crypto_bot
```

Windows tidak lagi dipakai untuk menjalankan Hermes/Pi Agent. Semua agent dipakai dari WSL.

## File Panduan yang Sudah Dibuat

Panduan utama:

```text
/home/officer/advanced_crypto_bot/advanced_crypto_bot/PANDUAN_HERMES_BOTPY.md
```

Isi panduan:

- Cara buka WSL
- Cara `source ~/hermes-pi.sh`
- Cara masuk folder project `bot.py`
- Cara pakai Hermes
- Cara pakai Termul Manager
- Prompt siap pakai untuk audit `bot.py`
- Prompt siap pakai untuk review bug BUY dan S1/S2/R1/R2
- Cara cek `git diff`
- Cara menjalankan test

## Status Windows

Install Hermes/Pi Agent Windows sudah dibersihkan.

Verifikasi terakhir:

```text
where pi          -> not found
where pi-agent    -> not found
where hermes      -> not found
where hermes-agent -> not found
```

Folder npm global Windows terkait Pi/Hermes juga sudah dihapus dari:

```text
C:\nvm4w\nodejs\node_modules
```

Port Windows `20128` juga kosong.

## Status WSL

WSL masih punya Hermes dan Pi:

```bash
source ~/hermes-pi.sh
which hermes
which pi
```

Hasil yang diharapkan:

```text
/home/officer/.hermes/bin/hermes
/home/officer/.npm-global/bin/pi
```

Dashboard yang seharusnya aktif:

```text
Hermes: http://127.0.0.1:9119
Pi:     http://127.0.0.1:8000
```

Gateway Pi:

```text
9999
```

Cek dari WSL:

```bash
ss -ltnp | grep -E ':8000|:9119|:9999'
```

## Termul Manager

Yang dimaksud user adalah Termul Manager dari:

```text
https://github.com/gnoviawan/termul/releases/
```

Termul dipakai sebagai terminal desktop. Hermes/Pi tetap dijalankan dari WSL.

Urutan Termul:

```text
Buka Termul
-> New Project
-> New Terminal
-> pilih WSL / Ubuntu
```

Kalau tidak ada pilihan WSL:

```powershell
wsl -d Ubuntu
```

Setelah masuk WSL:

```bash
source ~/hermes-pi.sh
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
```

## Masalah Hermes TUI

Hari ini Hermes TUI di tmux/Termul sempat blank dan tidak merespons prompt.

Prompt user sudah masuk ke pane Hermes, tetapi Hermes tidak memprosesnya.

Kemungkinan penyebab:

- TUI Hermes blank/stuck di Termul
- tmux/Termul memberi ukuran terminal aneh
- Hermes agent terminal macet walaupun dashboard hidup

Tanda yang terlihat:

```text
your 131072x1 screen size is bogus. expect trouble
```

## Cara Lanjut Setelah Restart Windows

### 1. Buka Termul atau Windows Terminal

Masuk WSL:

```powershell
wsl -d Ubuntu
```

### 2. Aktifkan Environment

```bash
source ~/hermes-pi.sh
```

Kalau tidak muncul apa-apa, itu normal.

Cek:

```bash
which hermes
which pi
tmux ls
```

### 3. Masuk Project

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
```

### 4. Coba Pakai Dashboard Hermes

Lebih stabil daripada TUI jika Termul blank:

```text
http://127.0.0.1:9119
```

Paste prompt di dashboard Hermes.

### 5. Kalau Mau Pakai tmux Hermes

```bash
tmux attach -t hermes-agent
```

Keluar tanpa mematikan:

```text
Ctrl+b lalu d
```

Kalau Hermes blank, restart hanya Hermes:

```bash
tmux kill-session -t hermes-agent
source ~/hermes-pi.sh
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
tmux new-session -s hermes-agent -x 120 -y 36 'cd /home/officer/advanced_crypto_bot/advanced_crypto_bot && hermes'
```

### 6. Alternatif Stabil: Pakai Pi Agent

Pi agent sebelumnya sudah lebih stabil dan modelnya berhasil menjawab.

```bash
tmux attach -t pi-agent
```

Lalu paste prompt yang sama.

## Prompt Pertama untuk Hermes/Pi

```text
Saya sedang bekerja di project:
/home/officer/advanced_crypto_bot/advanced_crypto_bot

Baca dulu semua file .md yang relevan di folder ini, lalu baca bot.py.
Jangan edit file dulu.

Tolong jelaskan:
1. alur kerja bot.py dari start sampai kirim sinyal
2. file mana saja yang mengatur keputusan BUY/SELL
3. bagian mana yang mengatur S1/S2/R1/R2
4. bagian mana yang berpotensi membuat BUY muncul terlalu jauh dari support
```

## Prompt Review Bug

```text
Sekarang review logika BUY dan support/resistance.
Cari kenapa bot bisa memberi BUY saat harga bukan di area S1/S2.
Jangan edit dulu.
Berikan daftar file dan line yang perlu diperbaiki.
```

## Prompt Izinkan Edit

```text
Silakan perbaiki bug itu.

Syarat:
- BUY hanya boleh lolos kalau harga berada di zona entry support S1-S2 atau toleransi dekat support
- S1/S2/R1/R2 harus urut benar
- jangan ubah API key
- jangan ubah file yang tidak terkait
- ikuti dokumentasi .md project

Setelah selesai:
- jelaskan file apa saja yang diubah
- jelaskan alasan perubahan
- jalankan test yang relevan
- tampilkan ringkasan hasil test
```

## Cek Setelah Agent Mengedit

```bash
git diff
python3 -m unittest discover -v
```

Test spesifik yang pernah dipakai:

```bash
python3 -m unittest tests.test_support_resistance_ordering tests.test_batch3_rule_rejections -v
```

## Catatan Penting

Selalu ingatkan agent:

```text
Jangan pakai path Windows.
Jangan pakai 9router.
Jangan ubah API key.
Jangan edit file sebelum membaca dokumentasi .md project.
Jangan ubah file yang tidak terkait tugas.
```

## Update Termul Error

Pada pengecekan lanjutan, sesi berikut masih hidup:

```text
hermes-dashboard -> http://127.0.0.1:9119
pi-dashboard     -> http://127.0.0.1:8000
pi gateway       -> port 9999
```

Pi dashboard sehat dan bisa dipakai. Hermes TUI sempat diam walau prompt sudah
masuk, jadi sesi `hermes-agent` sudah dibuat ulang dari WSL dengan ukuran tetap:

```bash
tmux kill-session -t hermes-agent
tmux new-session -d -s hermes-agent -x 120 -y 36 -c /home/officer/advanced_crypto_bot/advanced_crypto_bot /home/officer/.hermes/bin/hermes
```

Jika Termul menampilkan:

```text
your 131072x1 screen size is bogus. expect trouble
```

jalankan ini di terminal WSL Termul sebelum attach tmux:

```bash
stty rows 36 cols 120
export LINES=36
export COLUMNS=120
tmux attach -t pi-agent
```

Untuk Hermes, dashboard web biasanya lebih stabil daripada TUI:

```text
http://127.0.0.1:9119
```
