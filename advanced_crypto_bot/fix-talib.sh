#!/bin/bash

echo "🔧 Memperbaiki instalasi TA-Lib..."

# Install Python 3.10
echo "📦 Menginstall Python 3.10..."
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev

# Backup requirements jika ada
if [ -f "requirements.txt" ]; then
    cp requirements.txt requirements.txt.bak
fi

# Hapus venv lama
echo "🗑️ Menghapus venv lama..."
deactivate 2>/dev/null
rm -rf venv

# Buat venv baru
echo "🆕 Membuat venv baru dengan Python 3.10..."
python3.10 -m venv venv
source venv/bin/activate

# Install TA-Lib C library
echo "🔨 Mengompilasi TA-Lib C library..."
cd /tmp
wget -q https://sourceforge.net/projects/ta-lib/files/ta-lib/0.4.0/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib
./configure --prefix=/usr > /dev/null 2>&1
make > /dev/null 2>&1
sudo make install > /dev/null 2>&1
cd /tmp
rm -rf ta-lib*

# Install Python packages
echo "📦 Menginstall Python packages..."
pip install --upgrade pip
pip install ta-lib requests python-telegram-bot pandas numpy

# Verifikasi
echo "✅ Verifikasi instalasi..."
python -c "import talib; print(f'TA-Lib version: {talib.__version__}')" && echo "SUCCESS!" || echo "FAILED!"

echo "Selesai! Jalankan: source venv/bin/activate"