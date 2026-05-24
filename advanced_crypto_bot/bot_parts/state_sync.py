# Tujuan: Isolasi logic state watchlist dan preload historical agar konstruktor bot.py tetap ringkas.
# Caller: bot.AdvancedCryptoBot wrappers.
# Dependensi: threading, core.database.Database API, pandas DataFrame state in bot.
# Main Functions: load_watchlist_from_db, preload_historical_data, sync_watchlist_to_db, remove_watchlist_from_db, clear_watchlist_in_db.
# Side Effects: DB read/write, mutasi bot.subscribers dan bot.historical_data.

import threading


def load_watchlist_from_db(bot):
    try:
        watchlists = bot.db.get_all_watchlists()
        if watchlists:
            total_pairs = sum(len(pairs) for pairs in watchlists.values())
            bot._logger.info(f"📋 Loaded watchlist from DB: {total_pairs} pairs across {len(watchlists)} users")
        else:
            bot._logger.info("📋 No watchlist in DB (fresh start or all cleared)")
        return watchlists
    except Exception as e:
        bot._logger.error(f"❌ Failed to load watchlist from DB: {e}")
        return {}


def preload_historical_data(bot):
    def _preload():
        all_pairs = set()
        for user_pairs in bot.subscribers.values():
            all_pairs.update(user_pairs)

        if not all_pairs:
            bot._logger.info("📚 No pairs to preload")
            return

        bot._logger.info(f"📚 Preloading historical data for {len(all_pairs)} pairs...")
        loaded_count = 0

        for pair in all_pairs:
            try:
                df = bot.db.get_price_history(pair, limit=200)
                if not df.empty and len(df) >= 60:
                    bot.historical_data[pair] = df
                    loaded_count += 1
                    bot._logger.debug(f"  ✅ {pair}: {len(df)} candles loaded")
                elif not df.empty:
                    bot.historical_data[pair] = df
                    bot._logger.debug(f"  ⚠️  {pair}: {len(df)} candles (need 60+, accumulating...)")
                else:
                    bot._logger.debug(f"  ❌ {pair}: No data in DB yet")
            except Exception as e:
                bot._logger.error(f"  ❌ {pair}: Error loading data: {e}")

        bot._logger.info(f"📚 Preload complete: {loaded_count}/{len(all_pairs)} pairs ready (60+ candles)")

    preload_thread = threading.Thread(target=_preload, daemon=True, name="Preload-History")
    preload_thread.start()


def sync_watchlist_to_db(bot, user_id: int, pair: str):
    try:
        bot.db.add_to_watchlist(user_id, pair)
    except Exception as e:
        bot._logger.error(f"❌ Failed to sync watchlist to DB: {e}")


def remove_watchlist_from_db(bot, user_id: int, pair: str):
    try:
        bot.db.remove_from_watchlist(user_id, pair)
    except Exception as e:
        bot._logger.error(f"❌ Failed to remove watchlist from DB: {e}")


def clear_watchlist_in_db(bot, user_id: int = None):
    try:
        if user_id:
            bot.db.clear_watchlist(user_id)
        else:
            bot.db.clear_all_watchlists()
    except Exception as e:
        bot._logger.error(f"❌ Failed to clear watchlist in DB: {e}")
