#!/bin/bash

echo "🔧 Installing TA-Lib on WSL..."

# 1. Install build dependencies
echo "📦 Installing build tools..."
sudo apt update
sudo apt install -y build-essential wget

# 2. Download and build TA-Lib C library
echo "📥 Downloading TA-Lib C library..."
cd /tmp
wget https://sourceforge.net/projects/ta-lib/files/ta-lib/0.4.0/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib

echo "🔨 Compiling TA-Lib (this may take a minute)..."
./configure --prefix=/usr
make -j$(nproc)
sudo make install

# 3. Clean up
cd /tmp
rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# 4. Install Python package
echo "🐍 Installing Python wrapper..."
source ~/advanced_crypto_bot/venv/bin/activate
pip install numpy --upgrade
pip install ta-lib

# 5. Test
echo "✅ Testing installation..."
python -c "import talib; print(f'TA-Lib version: {talib.__version__}')" && echo "SUCCESS!" || echo "FAILED!"

echo "Done!"