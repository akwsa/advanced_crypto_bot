#!/bin/bash
# =============================================================================
# Package Bot for VPS Upload
# =============================================================================
# This script creates a clean package ready for VPS deployment
# Excludes: .env, databases, logs, cache, and other sensitive files
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
OUTPUT_DIR="$SCRIPT_DIR/dist"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ARCHIVE_NAME="crypto-bot-${TIMESTAMP}.tar.gz"

print_header "📦 Package Bot for VPS Upload"
echo ""

# Check if bot directory exists
if [ ! -d "$BOT_DIR" ]; then
    print_error "Bot directory not found: $BOT_DIR"
    exit 1
fi

print_success "Bot directory found: $BOT_DIR"
echo ""

# Create output directory
print_info "Creating output directory..."
mkdir -p "$OUTPUT_DIR"
print_success "Output directory: $OUTPUT_DIR"
echo ""

# Create temporary staging directory
print_info "Creating staging area..."
STAGING_DIR=$(mktemp -d)
print_success "Staging directory: $STAGING_DIR"
echo ""

# Copy bot files to staging (exclude sensitive files)
print_info "Copying bot files..."
rsync -av --progress \
    --exclude='.env' \
    --exclude='*.db' \
    --exclude='*.sqlite' \
    --exclude='*.sqlite3' \
    --exclude='*.log' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='venv' \
    --exclude='data/*.db' \
    --exclude='logs/' \
    --exclude='models/*.pkl' \
    --exclude='models/*.h5' \
    --exclude='models/*.pt' \
    --exclude='manual_sr_levels.json' \
    --exclude='.git' \
    --exclude='.gitignore' \
    --exclude='dist/' \
    --exclude='build/' \
    --exclude='.DS_Store' \
    --exclude='Thumbs.db' \
    "$BOT_DIR/" "$STAGING_DIR/advanced_crypto_bot/"

print_success "Bot files copied"
echo ""

# Copy documentation and scripts from parent directory
print_info "Copying documentation..."
cp "$SCRIPT_DIR/VPS_DEPLOYMENT_GUIDE.md" "$STAGING_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/MULTI_USER_GUIDE.md" "$STAGING_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/setup_vps.sh" "$STAGING_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/quick_start.sh" "$STAGING_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/README.md" "$STAGING_DIR/" 2>/dev/null || true
print_success "Documentation copied"
echo ""

# Ensure .env.example exists in staging
if [ -f "$STAGING_DIR/advanced_crypto_bot/.env.example" ]; then
    print_success ".env.example included"
else
    print_warning ".env.example not found"
fi
echo ""

# Create README for the package
print_info "Creating package README..."
cat > "$STAGING_DIR/README_FIRST.txt" << 'EOF'
================================================================================
  Advanced Crypto Trading Bot - VPS Package
================================================================================

📦 Package Contents:
  • advanced_crypto_bot/          - Main bot application
  • VPS_DEPLOYMENT_GUIDE.md       - Complete deployment guide
  • MULTI_USER_GUIDE.md           - Multi-user setup guide
  • setup_vps.sh                  - Automated VPS setup script
  • README.md                     - Main documentation

🚀 Quick Start:

1. Upload this package to your VPS:
   
   scp crypto-bot-*.tar.gz root@your-vps-ip:/opt/
   
2. SSH to VPS and extract:
   
   ssh root@your-vps-ip
   cd /opt
   tar -xzf crypto-bot-*.tar.gz
   
3. Run automated setup:
   
   cd crypto-bot
   bash setup_vps.sh
   
4. Configure .env:
   
   nano advanced_crypto_bot/.env
   
   Required settings:
   - TELEGRAM_BOT_TOKEN=your_token
   - ADMIN_IDS=123456789,987654321
   
5. Start bot:
   
   systemctl enable crypto-bot
   systemctl start crypto-bot
   systemctl status crypto-bot

📚 Documentation:
  • Read VPS_DEPLOYMENT_GUIDE.md for detailed instructions
  • Read MULTI_USER_GUIDE.md for multi-user setup
  
⚠️  Important:
  • Never commit .env to version control
  • Default mode: DRY_RUN=true (simulation)
  • For real trading: Configure API keys in .env
  
🔐 Security:
  • This package does NOT include:
    - .env (sensitive config)
    - Database files
    - Log files
    - ML model files (will be trained on first run)
  
📞 Support:
  • Telegram: @your_support_channel
  • Docs: Check included markdown files

================================================================================
EOF

print_success "Package README created"
echo ""

# Create archive
print_info "Creating compressed archive..."
cd "$STAGING_DIR"
tar -czf "$OUTPUT_DIR/$ARCHIVE_NAME" ./*
print_success "Archive created: $ARCHIVE_NAME"
echo ""

# Calculate file size
ARCHIVE_SIZE=$(du -h "$OUTPUT_DIR/$ARCHIVE_NAME" | cut -f1)
print_info "Archive size: $ARCHIVE_SIZE"
echo ""

# Calculate checksum
print_info "Calculating checksum..."
CHECKSUM=$(sha256sum "$OUTPUT_DIR/$ARCHIVE_NAME" | cut -d' ' -f1)
echo "$CHECKSUM  $ARCHIVE_NAME" > "$OUTPUT_DIR/${ARCHIVE_NAME}.sha256"
print_success "Checksum saved"
echo ""

# Cleanup staging
print_info "Cleaning up..."
rm -rf "$STAGING_DIR"
print_success "Cleanup complete"
echo ""

# Final summary
print_header "✅ Package Complete!"
echo ""
print_success "Package ready for VPS deployment!"
echo ""
echo "📦 Package Information:"
echo "   File: $ARCHIVE_NAME"
echo "   Size: $ARCHIVE_SIZE"
echo "   SHA256: ${CHECKSUM:0:16}..."
echo "   Location: $OUTPUT_DIR/"
echo ""
print_info "Next Steps:"
echo ""
echo "1️⃣  Upload to VPS:"
echo "   scp $OUTPUT_DIR/$ARCHIVE_NAME root@your-vps-ip:/opt/"
echo ""
echo "2️⃣  Or use rsync for faster upload:"
echo "   rsync -avz --progress $OUTPUT_DIR/$ARCHIVE_NAME root@your-vps-ip:/opt/"
echo ""
echo "3️⃣  Extract on VPS:"
echo "   ssh root@your-vps-ip"
echo "   cd /opt"
echo "   tar -xzf $ARCHIVE_NAME"
echo "   cd crypto-bot"
echo ""
echo "4️⃣  Run setup:"
echo "   bash setup_vps.sh"
echo ""
print_warning "⚠️  Remember to configure .env after upload!"
echo ""
print_header "Package Complete! 🎉"
