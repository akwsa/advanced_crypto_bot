#!/bin/bash
# =============================================================================
# Quick Start Script - Test Bot Locally Before VPS Upload
# =============================================================================
# Usage: bash quick_start.sh
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo -e "${BLUE}=================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}=================================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BOT_DIR="$SCRIPT_DIR/advanced_crypto_bot"

print_header "🚀 Advanced Crypto Bot - Quick Start"
echo ""

# Check if advanced_crypto_bot directory exists
if [ ! -d "$BOT_DIR" ]; then
    print_error "Bot directory not found: $BOT_DIR"
    exit 1
fi

cd "$BOT_DIR"
print_success "Changed to bot directory: $BOT_DIR"
echo ""

# Check Python
print_info "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed"
    print_info "Install with: sudo apt install python3 python3-pip python3-venv"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
print_success "Python found: $PYTHON_VERSION"
echo ""

# Create virtual environment if not exists
print_info "Setting up virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_success "Virtual environment created"
else
    print_success "Virtual environment already exists"
fi
echo ""

# Activate virtual environment
source venv/bin/activate
print_success "Virtual environment activated"
echo ""

# Install/update dependencies
print_info "Installing/updating dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
print_success "Dependencies installed"
echo ""

# Check .env file
print_info "Checking configuration..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        print_warning ".env created from .env.example"
        print_warning ""
        print_warning "⚠️  IMPORTANT: Configure .env before starting bot!"
        print_warning ""
        echo "Required settings:"
        echo "  1. TELEGRAM_BOT_TOKEN=your_token_from_@BotFather"
        echo "  2. ADMIN_IDS=your_telegram_user_id (get from @userinfobot)"
        echo ""
        read -p "Do you want to edit .env now? (y/n) " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ${EDITOR:-nano} .env
        else
            print_info "You can edit later with: nano $BOT_DIR/.env"
            exit 0
        fi
    else
        print_error ".env.example not found"
        exit 1
    fi
else
    print_success ".env file exists"
fi
echo ""

# Validate .env
print_info "Validating configuration..."
source .env 2>/dev/null || true

VALIDATION_FAILED=0

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ "$TELEGRAM_BOT_TOKEN" = "your_telegram_bot_token_here" ]; then
    print_error "TELEGRAM_BOT_TOKEN not configured"
    VALIDATION_FAILED=1
fi

if [ -z "$ADMIN_IDS" ] || [ "$ADMIN_IDS" = "your_telegram_user_id_here" ]; then
    print_error "ADMIN_IDS not configured"
    VALIDATION_FAILED=1
fi

if [ $VALIDATION_FAILED -eq 1 ]; then
    echo ""
    print_warning "Configuration incomplete!"
    print_info "Edit .env with: nano $BOT_DIR/.env"
    echo ""
    echo "Get your credentials:"
    echo "  • Bot Token: Message @BotFather on Telegram"
    echo "  • User ID: Message @userinfobot on Telegram"
    exit 1
fi

print_success "Configuration valid"
echo ""

# Create required directories
print_info "Creating data directories..."
mkdir -p data logs models
print_success "Directories created"
echo ""

# Final check
print_header "🎉 Ready to Start!"
echo ""
print_success "Bot is ready to run!"
echo ""
print_info "Configuration summary:"
echo "  • Bot Token: ${TELEGRAM_BOT_TOKEN:0:10}... (configured)"
echo "  • Admin IDs: $ADMIN_IDS"
echo "  • Watch Pairs: ${WATCH_PAIRS:-btcidr,ethidr,bridr}"
echo "  • Auto Trading: ${AUTO_TRADING_ENABLED:-false}"
echo "  • Dry Run Mode: ${AUTO_TRADE_DRY_RUN:-true}"
echo ""

# Ask if user wants to start now
read -p "Do you want to start the bot now? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Starting bot..."
    echo ""
    print_warning "Press Ctrl+C to stop the bot"
    echo ""
    sleep 2
    python3 bot.py
else
    print_info "To start the bot later, run:"
    echo ""
    echo "  cd $BOT_DIR"
    echo "  source venv/bin/activate"
    echo "  python3 bot.py"
    echo ""
    print_info "Or simply run: bash $SCRIPT_DIR/quick_start.sh"
fi
