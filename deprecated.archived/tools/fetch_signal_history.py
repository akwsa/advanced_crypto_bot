"""
Telegram Signal History Fetcher (SQLite Version)
=================================================
Script untuk mengambil signal LAMA (3 hari terakhir) dari bot Telegram
dan menyimpannya ke SQLite database.

KEUNGGULAN vs EXCEL:
- ✅ Lebih cepat (batch insert, single connection)
- ✅ Lebih aman (no file lock issues)
- ✅ Lebih efisien (indexes, queries)
- ✅ VPS-friendly (concurrent access OK)

CARA PAKAI:
    python fetch_signal_history.py
    
    # Export ke Excel kalau perlu
    python fetch_signal_history.py --export report.xlsx
"""

import re
import os
import logging
import argparse
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient
from signal_db import SignalDatabase

# ═══════════════════════════════════════════════════════════
#  KONFIGURASI — samakan dengan telegram_signal_saver.py
# ═══════════════════════════════════════════════════════════

API_ID       = 32920267           # Ganti dengan API ID kamu
API_HASH     = "829dacafd4194bbd3438906eccfdefa7"     # Ganti dengan API Hash kamu
SESSION_NAME = "signal_session"   # Harus sama dengan file session yang sudah ada

TARGET_BOT   = "@myownwebsocket_bot"   # Username bot yang dipantau
DB_FILE      = "data/signals.db"       # SQLite database file

HARI_KEBELAKANG = 3   # Ambil signal 3 hari terakhir

# ═══════════════════════════════════════════════════════════

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def parse_signal(text: str) -> dict:
    """Parse signal message dengan error handling yang baik."""
    
    # Strip HTML tags untuk parsing yang lebih mudah
    text_plain = re.sub(r'<[^>]+>', '', text)
    text_plain = re.sub(r'\s+', ' ', text_plain).strip()
    
    def find(pattern, default="—", text_source=None):
        """Find pattern in text, can use plain or original text"""
        try:
            source = text_source if text_source else text_plain
            m = re.search(pattern, source, re.IGNORECASE)
            if m:
                return m.group(1).strip()
            
            # Fallback ke original text jika tidak match di plain
            if text_source is None and text != text_plain:
                m = re.search(pattern, text, re.IGNORECASE)
                return m.group(1).strip() if m else default
            
            return default
        except Exception as e:
            logger.debug(f"Regex error for pattern '{pattern}': {e}")
            return default

    # Symbol: coba beberapa pattern (🚀 untuk STRONG_BUY, 📈 untuk BUY)
    symbol = find(r"🚀\s+([a-z]+idr)\s*-\s*Trading Signal")
    if symbol == "—":
        symbol = find(r"📈\s+([a-z]+idr)\s*-\s*Trading Signal")
    if symbol == "—":
        symbol = find(r"([a-z]+idr)\s*-\s*Trading Signal")
    
    # Price: handle angka dengan koma dan desimal
    price = find(r"Price:\s*([\d,]+\.?\d*)")
    if price == "—":
        price = find(r"💰.*?([\d,]+\.?\d*).*?IDR")
    
    # Recommendation: strict whitelist
    rec = find(r"Recommendation:\s*(STRONG_BUY|STRONG_SELL|BUY|SELL|HOLD)")
    if rec == "—":
        rec = find(r"🎯.*?(STRONG_BUY|STRONG_SELL|BUY|SELL|HOLD)")
    
    # Technical indicators
    rsi = find(r"RSI\s*\(14\):\s*(\w+)")
    macd = find(r"MACD:\s*(\w+)")
    ma = find(r"MA Trend:\s*(\w+)")
    bb = find(r"Bollinger:\s*(\w+)")
    vol = find(r"Volume:\s*(\w+)")
    
    # ML Prediction
    conf = find(r"Confidence:\s*([\d.]+)%?")
    
    # Pastikan confidence ada %
    if conf and conf != "—" and "%" not in conf:
        try:
            float(conf)
            conf += "%"
        except ValueError:
            conf = "—"
    
    strength = find(r"Combined Strength:\s*([\d.\-]+)")
    analysis = find(r"Analysis:\s*(.+?)(?:⏰|$)", text_source=text_plain)
    sig_time = find(r"⏰\s*([\d:]+)")
    
    # Validasi minimal: harus ada symbol
    if symbol == "—":
        logger.warning("⚠️  Symbol tidak ditemukan dalam pesan")
        logger.debug(f"Text preview: {text[:100]}...")
        return None
    
    # Normalize recommendation
    if rec and rec != "—":
        rec = rec.upper().strip()
    
    return dict(
        symbol=symbol.upper() if symbol != "—" else "—",
        price=price,
        rec=rec,
        rsi=rsi,
        macd=macd,
        ma=ma,
        bollinger=bb,
        volume=vol,
        confidence=conf,
        strength=strength,
        analysis=analysis,
        signal_time=sig_time
    )


async def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description="Fetch signal history from Telegram")
    parser.add_argument("--export", type=str, default="", help="Export to Excel file")
    parser.add_argument("--days", type=int, default=HARI_KEBELAKANG, help="Days to fetch")
    parser.add_argument("--no-clear", action="store_true", help="Don't clear database before fetch")
    args = parser.parse_args()
    
    days = args.days
    # Mundurin periodenya: default 7 hari (bukan 3) untuk dapat lebih banyak signal
    if days == 3:
        days = 7  # Default ke 7 hari
    
    batas_waktu = datetime.now(timezone.utc) - timedelta(days=days)

    logger.info("=" * 70)
    logger.info(f"  TELEGRAM SIGNAL HISTORY FETCHER (SQLite)")
    logger.info("=" * 70)
    logger.info(f"  Bot     : {TARGET_BOT}")
    logger.info(f"  Database: {DB_FILE}")
    logger.info(f"  Period  : Last {days} days")
    logger.info(f"  From    : {batas_waktu.strftime('%Y-%m-%d %H:%M')} UTC")
    logger.info("=" * 70)

    # Initialize SQLite database
    db = SignalDatabase(DB_FILE)
    
    # CLEAR DATABASE sebelum fetch (kecuali --no-clear)
    if not args.no_clear:
        logger.info(f"\n🗑️ Clearing database before fetch...")
        # Delete data (with commit)
        with db.get_connection(autocommit=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM signals")
            old_count = cursor.fetchone()['cnt']
            cursor.execute("DELETE FROM signals")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='signals'")  # Reset autoincrement
        logger.info(f"✅ Deleted {old_count} old signals")
        
        # VACUUM harus di luar transaction (reclaim space)
        db.vacuum()
        logger.info(f"✅ Database cleared and vacuumed!")
    else:
        stats = db.get_stats()
        if stats["total_signals"] > 0:
            logger.info(f"📊 Existing signals in DB: {stats['total_signals']}")
    
    logger.info(f"✅ Database initialized: {DB_FILE}")

    # Connect to Telegram
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    try:
        await client.connect()
    except Exception as e:
        logger.error(f"❌ Gagal connect ke Telegram: {e}")
        return

    # Cek session valid
    if not await client.is_user_authorized():
        logger.warning("⚠️  Session belum ada atau tidak valid!")
        logger.info("📱 Memulai login ke Telegram...")
        
        try:
            await client.start(
                phone=lambda: input("Masukkan nomor HP (+62xxx): "),
                password=lambda: input("Masukkan password 2FA (jika ada): "),
                code_callback=lambda: input("Masukkan kode OTP dari Telegram: ")
            )
            logger.info("✅ Login berhasil! Session disimpan.")
        except Exception as e:
            logger.error(f"❌ Login gagal: {e}")
            await client.disconnect()
            return

    try:
        logger.info("\n[INFO] Mengambil pesan dari Telegram...\n")

        messages_found = []
        total_checked = 0
        skipped_no_signal = 0

        async for message in client.iter_messages(TARGET_BOT, offset_date=None, reverse=False):
            total_checked += 1
            
            # Stop jika sudah melebihi batas waktu
            if message.date and message.date < batas_waktu:
                logger.info(f"[INFO] Reached cutoff date: {message.date.strftime('%Y-%m-%d')}")
                break

            text = message.text or ""
            
            # Deteksi signal - LEBIH LONGGAR
            # Cukup ada "Trading Signal" ATAU "Signal Alert"
            if "Trading Signal" in text or "Signal Alert" in text:
                messages_found.append(message)
            # Fallback: cek emoji + kata kunci
            elif ("📊" in text or "🚀" in text or "📈" in text) and \
                 ("Signal" in text or "signal" in text.lower()):
                messages_found.append(message)
            else:
                skipped_no_signal += 1

        # Balik urutan: terlama ke terbaru
        messages_found.reverse()

        logger.info(f"[INFO] Scan summary:")
        logger.info(f"   • Total messages checked: {total_checked}")
        logger.info(f"   • Signal messages found: {len(messages_found)}")
        logger.info(f"   • Skipped (not signal): {skipped_no_signal}")
        
        if not messages_found:
            logger.warning("[WARNING] Tidak ada signal ditemukan!")
            logger.info("Tips:")
            logger.info("  • Pastikan TARGET_BOT benar")
            logger.info("  • Cek apakah bot mengirim signal dalam period ini")
            logger.info("  • Coba tambah --days 14 atau --days 30")
            return

        logger.info(f"\n[INFO] Parsing {len(messages_found)} signals...\n")
        
        # Parse semua signal
        signals_to_insert = []
        parse_failed = 0
        
        for i, message in enumerate(messages_found, 1):
            try:
                data = parse_signal(message.text)
                
                if data is None:
                    logger.warning(f"  ⚠️  Skip #{i}: parsing gagal")
                    parse_failed += 1
                    continue

                # Gunakan waktu pesan asli dari Telegram
                received_at = message.date.astimezone().replace(tzinfo=None)

                # Override signal_time jika parse gagal
                if data["signal_time"] == "—":
                    data["signal_time"] = received_at.strftime("%H:%M:%S")
                
                signals_to_insert.append((data, received_at))
                
            except Exception as e:
                logger.error(f"  ❌ Error parsing message #{i}: {e}")
                parse_failed += 1
                continue
        
        logger.info(f"[INFO] Parsed: {len(signals_to_insert)} valid, {parse_failed} failed")
        
        # Batch insert ke SQLite (EFISIEN - single connection)
        if signals_to_insert:
            logger.info(f"\n[INFO] Inserting {len(signals_to_insert)} signals to SQLite (batch)...")
            inserted = db.insert_signals_batch(signals_to_insert)
            
            logger.info(f"\n{'=' * 70}")
            logger.info(f"[SELESAI] {inserted} signal baru ditambahkan ke database")
            logger.info(f"[INFO] Database: {DB_FILE}")
            logger.info(f"{'=' * 70}")
            
            # Show updated stats
            stats = db.get_stats()
            logger.info(f"\n📊 Database Statistics:")
            logger.info(f"   Total signals: {stats['total_signals']}")
            logger.info(f"   By recommendation:")
            for rec, count in stats['by_recommendation'].items():
                logger.info(f"     • {rec}: {count}")
            logger.info(f"   Top symbols:")
            for sym, count in list(stats['top_symbols'].items())[:5]:
                logger.info(f"     • {sym}: {count}")
            
            # Export to Excel kalau diminta
            if args.export:
                logger.info(f"\n📄 Exporting to Excel: {args.export}")
                db.export_to_excel(args.export)
                logger.info(f"✅ Export complete!")
        else:
            logger.info("[INFO] Tidak ada signal valid untuk disimpan")

    except Exception as e:
        logger.error(f"❌ Error utama: {e}", exc_info=True)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
