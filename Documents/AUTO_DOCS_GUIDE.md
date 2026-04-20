# Auto Documentation Generator

## Overview
Script `generate_docs.py` akan **otomatis scan** semua command di source code dan **generate** dokumentasi lengkap ke `README_COMMANDS.txt`.

## Kapan Harus Regenerate Documentation?

Setiap kali kamu:
- ✅ Menambah command baru (`/newcommand`)
- ✅ Menghapus command yang ada
- ✅ Mengubah nama command
- ✅ Mengubah parameter command
- ✅ Update docstring di method

## Cara Pakai

### 1. Buka Command Prompt / Terminal
```bash
cd c:\advanced-crypto-bot
```

### 2. Run Generator
```bash
python generate_docs.py
```

### 3. Check Output
```
🚀 Documentation Generator Starting...
============================================================
🔍 Scanning for commands...
✅ Found 31 bot commands
✅ Found 18 scalper commands

📝 Generating documentation...

============================================================
✅ Documentation generated successfully!
📄 Output: README_COMMANDS.txt
📊 Commands documented: 31 bot + 18 scalper
============================================================
```

### 4. View Documentation
```bash
notepad README_COMMANDS.txt
# atau
code README_COMMANDS.txt
```

## Otomatisasi dengan Git Hook

Kalau pakai Git, bisa setup **pre-commit hook** untuk auto-generate:

### 1. Buat file `.git/hooks/pre-commit`
```bash
#!/bin/sh
python generate_docs.py
git add README_COMMANDS.txt
```

### 2. Make executable (Linux/Mac)
```bash
chmod +x .git/hooks/pre-commit
```

### 3. Windows Alternative: `.git\hooks\pre-commit.bat`
```batch
@echo off
python generate_docs.py
git add README_COMMANDS.txt
```

Sekarang setiap commit, dokumentasi otomatis di-update!

## Cara Kerja Script

### Step 1: Scan Source Code
```python
# Scan bot.py
bot_commands = extract_commands_from_file('bot.py')

# Scan scalper_module.py
scalper_commands = extract_commands_from_file('scalper_module.py')
```

### Step 2: Extract Command Info
Script mencari pattern:
```python
CommandHandler("command_name", self.method_name)
```

Contoh:
```python
self.app.add_handler(CommandHandler("watch", self.watch))
self.app.add_handler(CommandHandler("buy", self.cmd_buy))
```

### Step 3: Extract Docstrings
Script ambil docstring dari method:
```python
async def watch(self, update, context):
    """Subscribe to real-time updates for one or more pairs"""
    # ...
```

### Step 4: Generate Documentation
Format output jadi sections:
```
================================================================================
1️⃣ BOT COMMANDS - WATCHLIST & MONITORING
================================================================================

/watch
    ➤ Subscribe to real-time updates for one or more pairs
    ➤ Method: watch
    ➤ Supports multiple pairs: /watch btcidr, ethidr, solidr
```

### Step 5: Write to File
Simpan ke `README_COMMANDS.txt`

## Struktur Output

```
README_COMMANDS.txt
├── Header (timestamp, version)
├── Table of Contents
├── Section 1: Watchlist & Monitoring
├── Section 2: Trading & Portfolio
├── Section 3: Auto Trading & Admin
├── Section 4: Scalper Buy/Sell
├── Section 5: Position Management
├── Section 6: Analysis & Info
├── Section 7: Pair Management
├── Section 8: Quick Workflows
├── Section 9: Important Notes
├── Section 10: Troubleshooting
└── Footer (version history)
```

## Customization

### Tambah Section Baru
Edit file `generate_docs.py`, cari method `generate_fresh_docs()`:

```python
# Tambah section baru
lines.append("=" * 80)
lines.append("NEW SECTION TITLE")
lines.append("=" * 80)
lines.append("")

# Add commands
for cmd_name in ['new_cmd1', 'new_cmd2']:
    cmd = next((c for c in bot_commands if c['command'] == f'/{cmd_name}'), None)
    if cmd:
        lines.append(f"{cmd['command']}")
        if cmd['docstring']:
            lines.append(f"    ➤ {cmd['docstring']}")
        lines.append("")
```

### Ubah Format Output
Cari bagian yang generate lines:

```python
# Format default
lines.append(f"{cmd['command']}")
lines.append(f"    ➤ {cmd['docstring']}")

# Bisa diubah jadi markdown, HTML, dll
```

### Tambah Info Tambahan
Bisa inject manual content setelah auto-generate:

```python
def generate_fresh_docs(self, bot_commands, scalper_commands):
    # ... auto-generated content ...
    
    # Add manual notes
    lines.append("\n⚠️ MANUAL NOTE:")
    lines.append("    This is additional info not in code...")
    
    return '\n'.join(lines)
```

## Scheduling (Optional)

Bisa setup auto-run setiap jam dengan Task Scheduler (Windows):

### 1. Buka Task Scheduler
```
Win + R → taskschd.msc
```

### 2. Create Basic Task
- **Name**: `CryptoBot Docs Generator`
- **Trigger**: Daily, repeat every 1 hour
- **Action**: Start a program
  - **Program**: `python.exe`
  - **Arguments**: `c:\advanced-crypto-bot\generate_docs.py`
  - **Start in**: `c:\advanced-crypto-bot`

## Benefits

### ✅ Always Up-to-Date
- Documentation selalu sinkron dengan code
- Tidak ada manual update yang ketinggalan

### ✅ Time Saving
- Tidak perlu edit README manual
- Tinggal run script

### ✅ Error Prevention
- Format konsisten
- Tidak ada typo atau missing commands

### ✅ Version Tracking
- Timestamp di setiap generate
- Bisa track changes

## Troubleshooting

### Q: Script error "File not found"
**A:** Pastikan run dari directory yang benar:
```bash
cd c:\advanced-crypto-bot
python generate_docs.py
```

### Q: Command tidak muncul di docs
**A:** Check:
1. Command terdaftar di `_register_handlers()` atau `_setup_handlers()`
2. Format: `CommandHandler("command_name", self.method_name)`
3. Method punya docstring

### Q: Docstring tidak muncul
**A:** Pastikan method punya docstring:
```python
async def watch(self, update, context):
    """This docstring will appear in docs"""
    # ...
```

Bukan:
```python
async def watch(self, update, context):
    # This comment won't appear
    # ...
```

### Q: Format output berantakan
**A:** Edit `generate_docs.py` method `generate_fresh_docs()` dan adjust formatting.

## Best Practices

### 1. Regenerate Setelah Update Code
```bash
# Setelah tambah/edit command
python generate_docs.py
```

### 2. Commit Bersamaan
```bash
git add bot.py scalper_module.py README_COMMANDS.txt
git commit -m "Add /buy command alias"
```

### 3. Review Hasil
```bash
# Check output
cat README_COMMANDS.txt | head -50
```

### 4. Backup Old Docs
```bash
# Sebelum generate
copy README_COMMANDS.txt README_COMMANDS.txt.bak

# Generate baru
python generate_docs.py

# Compare kalau perlu
diff README_COMMANDS.txt.bak README_COMMANDS.txt
```

## Example Workflow

```bash
# 1. Tambah command baru di bot.py
#    self.app.add_handler(CommandHandler("newcmd", self.new_cmd))

# 2. Add method dengan docstring
#    async def new_cmd(self, update, context):
#        """This is my new command"""
#        ...

# 3. Test command di bot

# 4. Generate docs
python generate_docs.py

# 5. Check hasil
notepad README_COMMANDS.txt

# 6. Commit
git add bot.py README_COMMANDS.txt
git commit -m "Add /newcmd command"
```

## Files

| File | Purpose |
|------|---------|
| `generate_docs.py` | Generator script |
| `README_COMMANDS.txt` | Generated documentation |
| `bot.py` | Source: Bot commands |
| `scalper_module.py` | Source: Scalper commands |

## Related Documentation

- `README_COMMANDS.txt` - Main documentation (auto-generated)
- `COMMANDS_GUIDE.md` - Original manual guide
- `AUTO_ADD_SCALPER_FEATURE.md` - Feature docs
- `SCALPER_BUTTON_FIX.md` - Bug fix docs

## Support

Kalau ada issue dengan generator:
1. Check error message
2. Verify bot.py dan scalper_module.py syntax
3. Run: `python -m py_compile generate_docs.py`
4. Check Python version: `python --version` (need 3.7+)
