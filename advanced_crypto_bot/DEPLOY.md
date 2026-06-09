# Deploy ke Google Cloud VM

## Server Specs
- VM: `mybot-hostbot2026`
- IP: `34.92.30.121`
- User: `wkagung`
- OS: Debian (Python 3.13)
- Specs: 2 core, 8GB RAM, 60GB SSD

## Langkah Deploy

### 1. Install dependencies di VM

```bash
sudo apt update && sudo apt install -y git tmux
```

### 2. Clone repository

```bash
git clone https://github.com/akwsa/advanced_crypto_bot.git
cd advanced_crypto_bot
git checkout fix/scalper-sltp-telegram-ui
cd advanced_crypto_bot
```

### 3. Setup Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Buat folder yang dibutuhkan

```bash
mkdir -p data models
```

### 5. Buat file .env

```bash
cat > .env << 'EOF'
# Paste isi .env disini
EOF
```

### 6. Transfer database & model dari WSL

Di WSL lokal:
```bash
cd ~/advanced_crypto_bot/advanced_crypto_bot
tar czf /tmp/bot-data.tar.gz data/trading.db data/signals.db models/trading_model_v2.pkl models/trading_model_v4.pkl
scp /tmp/bot-data.tar.gz wkagung@34.92.30.121:~/
```

Di VM Google:
```bash
tar xzf ~/bot-data.tar.gz -C ~/advanced_crypto_bot/advanced_crypto_bot/
```

### 7. Jalankan bot dalam tmux

```bash
tmux new -s bot
cd ~/advanced_crypto_bot/advanced_crypto_bot
source venv/bin/activate
python bot.py
```

- Detach: `Ctrl+B` lalu `D`
- Reconnect: `tmux attach -t bot`

## SSH Access dari WSL

SSH key sudah di-setup:
```bash
# WSL key: ~/.ssh/id_ed25519
# Sudah ditambahkan ke VM ~/.ssh/authorized_keys
ssh wkagung@34.92.30.121
```

## Notes

- Redis tidak perlu di-install — bot auto fallback ke dict in-memory
- Bot start dalam mode **DRY RUN** secara default
- Menutup SSH/browser tidak menghentikan bot (tmux background)
- **Stop/shutdown VM** dari GCP Console akan menghentikan bot
