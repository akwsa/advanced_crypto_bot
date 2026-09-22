# Panduan Memakai Hermes untuk Project bot.py

Panduan ini untuk menjalankan dan memakai Hermes dari WSL untuk project:

```text
/home/officer/advanced_crypto_bot/advanced_crypto_bot
```

Gunakan semua perintah dari WSL. Jangan jalankan Hermes/Pi dari Windows.

## 1. Buka WSL

Dari Windows Terminal atau PowerShell:

```powershell
wsl -d Ubuntu
```

## 2. Aktifkan Environment Hermes/Pi

Di dalam WSL:

```bash
source ~/hermes-pi.sh
```

## 3. Masuk ke Folder Project

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
```

## 4. Cek Hermes Tersedia

```bash
which hermes
```

Hasil yang benar kira-kira:

```text
/home/officer/.hermes/bin/hermes
```

Jika kosong, jalankan ulang:

```bash
source ~/hermes-pi.sh
which hermes
```

## 5. Jalankan Hermes

```bash
hermes
```

Jika Hermes sudah berjalan di tmux:

```bash
tmux attach -t hermes-agent
```

Keluar dari tmux tanpa mematikan Hermes:

```text
Ctrl+b lalu d
```

Dashboard Hermes bisa dibuka dari browser Windows:

```text
http://127.0.0.1:9119
```

## 6. Perintah Pertama untuk Hermes

Copy paste prompt ini ke Hermes:

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

Tujuan langkah ini: Hermes memahami project dulu sebelum mengubah kode.

## 7. Minta Review Bug

Setelah Hermes menjelaskan alurnya, copy paste prompt ini:

```text
Sekarang review logika BUY dan support/resistance.
Cari kenapa bot bisa memberi BUY saat harga bukan di area S1/S2.
Jangan edit dulu.
Berikan daftar file dan line yang perlu diperbaiki.
```

Tujuan langkah ini: jangan langsung edit. Minta Hermes menunjukkan masalahnya dulu.

## 8. Izinkan Hermes Mengedit

Kalau hasil review Hermes masuk akal, copy paste prompt ini:

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

## 9. Cek Hasil Edit dari WSL

Masih di folder project:

```bash
git diff
```

Periksa apakah perubahan hanya menyentuh file yang memang terkait bug.

## 10. Jalankan Test

```bash
python3 -m unittest discover -v
```

Jika ingin menjalankan test yang lebih spesifik:

```bash
python3 -m unittest tests.test_support_resistance_ordering tests.test_batch3_rule_rejections -v
```

## 11. Kalau Test Gagal

Copy error test, lalu paste ke Hermes:

```text
Test gagal dengan output berikut:

[PASTE ERROR DI SINI]

Perbaiki tanpa mengubah API key dan tanpa mengubah file yang tidak terkait.
Setelah itu jalankan ulang test yang relevan.
```

## 12. Urutan Singkat

```text
WSL
-> source ~/hermes-pi.sh
-> cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
-> hermes
-> suruh baca .md + bot.py
-> suruh review bug
-> baru izinkan edit
-> git diff
-> python3 -m unittest discover -v
```

## 13. Aturan Aman

Selalu ingatkan Hermes:

```text
Jangan pakai path Windows.
Jangan pakai 9router.
Jangan ubah API key.
Jangan edit file sebelum membaca dokumentasi .md project.
Jangan ubah file yang tidak terkait tugas.
```

## 14. Prompt Siap Pakai untuk Audit bot.py

```text
Baca dokumentasi .md project dan bot.py.
Audit alur sinyal trading.
Fokus pada:
- BUY yang terlalu longgar
- support/resistance S1/S2/R1/R2 yang salah urut
- risk/reward yang menipu
- confidence yang terlalu tinggi
- ML score yang mengalahkan rule teknikal

Jangan edit dulu.
Berikan temuan dengan file dan line.
```

## 15. Prompt Siap Pakai untuk Perbaikan

```text
Perbaiki temuan yang sudah kamu jelaskan.

Batasan:
- BUY hanya boleh muncul dekat support entry zone
- resistance harus R1 < R2
- support harus S2 < S1
- jangan ubah API key
- jangan ubah scheduler kecuali memang terkait
- jangan ubah format Telegram kecuali perlu untuk memperbaiki output S/R

Setelah edit:
- jalankan test
- tunjukkan ringkasan diff
- jelaskan risiko perubahan
```

## 16. Memakai Termul Manager

Bagian ini untuk Termul Manager dari:

```text
https://github.com/gnoviawan/termul/releases/
```

Termul adalah aplikasi terminal manager desktop. Jadi cara pakainya mirip Windows Terminal, tetapi lebih enak untuk workspace, tab, split pane, editor, dan browser internal.

Hermes dan Pi tetap berjalan dari WSL. Termul hanya dipakai sebagai terminalnya.

Alur utamanya:

```text
Termul
-> buka project advanced_crypto_bot
-> buat terminal WSL Ubuntu
-> source ~/hermes-pi.sh
-> cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
-> attach Hermes atau jalankan hermes
```

### 16.1. Install Termul di Windows

Download installer Windows dari halaman releases.

Untuk Windows, pilih file:

```text
Termul.Manager_0.3.8_x64-setup.exe
```

Versi terbaru yang terlihat saat panduan ini dibuat adalah:

```text
Termul Manager v0.3.8
```

Setelah download:

```text
Double click installer
-> ikuti proses install
-> buka Termul Manager
```

### 16.2. Buat Project/Workspace Termul

Di Termul:

```text
Klik tombol +
-> Create Project / New Project
-> pilih workspace directory
```

Kalau Termul meminta folder Windows, pilih folder yang mudah, misalnya:

```text
C:\Users\officer\Documents\Codex
```

Catatan: project bot tetap berada di WSL:

```text
/home/officer/advanced_crypto_bot/advanced_crypto_bot
```

Folder Windows di Termul hanya untuk workspace Termul, bukan lokasi bot.

### 16.3. Buka Terminal WSL di Termul

Buat terminal baru di Termul.

Kalau ada pilihan shell:

```text
Pilih WSL / Ubuntu
```

Kalau tidak ada pilihan WSL, jalankan manual di terminal Termul:

```powershell
wsl -d Ubuntu
```

Setelah masuk WSL, prompt biasanya berubah menjadi user Linux, misalnya:

```text
officer@...
```

### 16.4. Aktifkan Environment Hermes/Pi

Di terminal WSL dalam Termul:

```bash
source ~/hermes-pi.sh
```

Cek binary yang benar:

```bash
which hermes
which pi
which codex
which opencode
```

Hasil yang diharapkan:

```text
/home/officer/.hermes/bin/hermes
/home/officer/.npm-global/bin/pi
/home/officer/.npm-global/bin/codex
/home/officer/.npm-global/bin/opencode
```

Kalau hasilnya mengarah ke `/mnt/c/...`, berarti kamu belum masuk environment WSL yang benar. Jalankan ulang:

```bash
source ~/hermes-pi.sh
```

### 16.5. Masuk ke Folder Project bot.py

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
```

Cek file:

```bash
ls
ls *.md
ls bot.py
```

### 16.6. Pakai Hermes yang Sudah Berjalan

Kalau Hermes sudah berjalan di tmux:

```bash
tmux attach -t hermes-agent
```

Keluar dari tmux tanpa mematikan Hermes:

```text
Ctrl+b lalu d
```

Kalau ingin menjalankan Hermes baru:

```bash
hermes
```

### 16.7. Pakai Dashboard di Termul Browser

Termul punya browser tab internal. Kamu bisa buka:

```text
http://127.0.0.1:9119
```

Untuk Pi dashboard:

```text
http://127.0.0.1:8000
```

Jika dashboard tidak muncul, cek dari terminal WSL:

```bash
ss -ltnp | grep -E ':8000|:9119|:9999'
```

Kalau belum aktif:

```bash
source ~/hermes-pi.sh
```

### 16.8. Prompt Pertama untuk Hermes dari Termul

Paste ini ke Hermes:

```text
Saya memakai Termul Manager, terminalnya masuk ke WSL Ubuntu.
Project ada di:
/home/officer/advanced_crypto_bot/advanced_crypto_bot

Jangan pakai path Windows.
Jangan pakai 9router.
Jangan ubah API key.

Baca dulu file .md yang relevan, lalu baca bot.py.
Jangan edit dulu.

Jelaskan:
1. alur bot.py dari start sampai kirim sinyal-
2. file yang mengatur BUY/SELL
3. file yang mengatur S1/S2/R1/R2
4. risiko BUY muncul terlalu jauh dari support
```

### 16.9. Prompt Review Bug

Setelah Hermes memahami project, paste:

```text
Sekarang review logika BUY dan support/resistance.
Cari kenapa bot bisa memberi BUY saat harga bukan di area S1/S2.
Jangan edit dulu.
Berikan daftar file dan line yang perlu diperbaiki.
```

### 16.10. Prompt Izinkan Edit

Kalau review Hermes masuk akal:

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
- jalankan test yang relevan
- tampilkan ringkasan hasil test
```

### 16.11. Layout Termul yang Enak untuk Project Ini

Gunakan 3 pane/tab:

```text
Pane 1: Hermes
Pane 2: shell biasa untuk git diff dan test
Pane 3: browser dashboard Hermes/Pi
```

Pane 2 command:

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
git diff
python3 -m unittest discover -v
```

Browser internal:

```text
http://127.0.0.1:9119
http://127.0.0.1:8000
```

### 16.12. Urutan Singkat Termul

```text
Buka Termul
-> New Project
-> New Terminal
-> pilih WSL / Ubuntu, atau ketik: wsl -d Ubuntu
-> source ~/hermes-pi.sh
-> cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
-> tmux attach -t hermes-agent
-> paste prompt baca .md + bot.py
-> minta review
-> baru izinkan edit
-> cek git diff
-> jalankan test
```
