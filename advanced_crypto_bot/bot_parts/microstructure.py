# Tujuan: Kumpulan helper microstructure/order execution agar bot.py tidak menumpuk logic trading rendah-level.
# Caller: bot.AdvancedCryptoBot wrappers, autotrade.runtime via bot methods.
# Dependensi: core.config.Config, pandas, time, bot.indodax.
# Main Functions: detect_spoofing, update_heatmap, find_liquidity_zones, smart_order_routing, elite_signal, split_order, execute_single_order, fee_aware_net_price.
# Side Effects: membaca/menulis state in-memory bot (spoof_tracker, heatmap_data), call HTTP order placement via bot.indodax.

import time

from core.config import Config


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_chunks():
    chunks = int(_safe_float(getattr(Config, "SMART_ROUTING_CHUNKS", 1), 1))
    return max(1, chunks)


def detect_spoofing(bot, pair: str, bids: list, asks: list) -> tuple:
    if not Config.SPOOFING_ENABLED:
        return bids[:10], asks[:10], False

    if pair not in bot.spoof_tracker:
        bot.spoof_tracker[pair] = {}

    for price, vol in bids[:10]:
        price_f = _safe_float(price)
        vol_f = _safe_float(vol)
        if price_f <= 0 or vol_f < 0:
            continue
        price_key = round(price_f, -3)

        if price_key not in bot.spoof_tracker[pair]:
            bot.spoof_tracker[pair][price_key] = {"vol": vol_f, "seen": 1, "type": "bid"}
        else:
            bot.spoof_tracker[pair][price_key]["seen"] += 1
            bot.spoof_tracker[pair][price_key]["vol"] = vol_f

    for price, vol in asks[:10]:
        price_f = _safe_float(price)
        vol_f = _safe_float(vol)
        if price_f <= 0 or vol_f < 0:
            continue
        price_key = round(price_f, -3)

        if price_key not in bot.spoof_tracker[pair]:
            bot.spoof_tracker[pair][price_key] = {"vol": vol_f, "seen": 1, "type": "ask"}
        else:
            bot.spoof_tracker[pair][price_key]["seen"] += 1
            bot.spoof_tracker[pair][price_key]["vol"] = vol_f

    cleaned_bids = []
    cleaned_asks = []
    spoof_detected = False
    prices_to_remove = []

    for price_key, data in bot.spoof_tracker[pair].items():
        if data["seen"] >= Config.SPOOFING_MIN_PERSISTENCE:
            if data["type"] == "bid":
                cleaned_bids.append((price_key, data["vol"]))
            else:
                cleaned_asks.append((price_key, data["vol"]))
        else:
            spoof_detected = True
            if data["seen"] < 2:
                prices_to_remove.append(price_key)

    for pk in prices_to_remove:
        if pk in bot.spoof_tracker.get(pair, {}):
            del bot.spoof_tracker[pair][pk]

    if spoof_detected:
        bot._logger.info(f"🚨 Spoofing detected for {pair}: {len(prices_to_remove)} fake walls removed")

    return cleaned_bids[:10], cleaned_asks[:10], spoof_detected


def update_heatmap(bot, pair: str, bids: list, asks: list):
    if not Config.HEATMAP_ENABLED:
        return

    if pair not in bot.heatmap_data:
        bot.heatmap_data[pair] = []

    snapshot = {
        "time": time.time(),
        "bids": [(_safe_float(p), _safe_float(v)) for p, v in bids[:15] if _safe_float(p) > 0 and _safe_float(v) >= 0],
        "asks": [(_safe_float(p), _safe_float(v)) for p, v in asks[:15] if _safe_float(p) > 0 and _safe_float(v) >= 0],
    }

    bot.heatmap_data[pair].append(snapshot)
    if len(bot.heatmap_data[pair]) > Config.HEATMAP_MAX_SNAPSHOTS:
        bot.heatmap_data[pair] = bot.heatmap_data[pair][-Config.HEATMAP_MAX_SNAPSHOTS:]


def find_liquidity_zones(bot, pair: str) -> list:
    if pair not in bot.heatmap_data or not bot.heatmap_data[pair]:
        return []

    levels = {}
    rounding = Config.HEATMAP_PRICE_ROUNDING

    for snap in bot.heatmap_data[pair]:
        for price, vol in snap["bids"] + snap["asks"]:
            key = round(price, -len(str(rounding)) + 1) if rounding > 0 else round(price)
            key = int(key)
            levels[key] = levels.get(key, 0) + vol

    zones = sorted(levels.items(), key=lambda x: x[1], reverse=True)
    return zones[: Config.HEATMAP_TOP_ZONES]


def smart_order_routing(pair: str, side: str, total_size: float, bids: list, asks: list) -> list:
    if not Config.SMART_ROUTING_ENABLED:
        if side == "buy" and asks:
            return [(_safe_float(asks[0][0]), total_size)]
        if side == "sell" and bids:
            return [(_safe_float(bids[0][0]), total_size)]
        return [(0, total_size)]

    chunks = _safe_chunks()
    size_per_chunk = total_size / chunks
    results = []

    for i in range(chunks):
        if side == "buy":
            if i < len(asks):
                best_ask = _safe_float(asks[i][0])
                if best_ask <= 0:
                    continue
                improved_price = best_ask * (1 - Config.SMART_ROUTING_PRICE_IMPROVEMENT)
                results.append((improved_price, size_per_chunk))
        else:
            if i < len(bids):
                best_bid = _safe_float(bids[i][0])
                if best_bid <= 0:
                    continue
                improved_price = best_bid * (1 + Config.SMART_ROUTING_PRICE_IMPROVEMENT)
                results.append((improved_price, size_per_chunk))

    return results


def elite_signal(df, bids, asks, zones) -> tuple:
    if df.empty or len(df) < 10:
        return "HOLD", 0.5, "NEUTRAL"

    current_price = df["close"].iloc[-1]
    ma10 = df["close"].rolling(10).mean().iloc[-1]
    probability = 0.7 if current_price > ma10 else 0.3
    bid_vol = sum(_safe_float(x[1]) for x in (bids or [])[:5])
    ask_vol = sum(_safe_float(x[1]) for x in (asks or [])[:5])
    imbalance = "BUY" if bid_vol > ask_vol else "SELL"

    if zones:
        nearest_zone = zones[0][0]
        distance_pct = abs(current_price - nearest_zone) / current_price
        if distance_pct < Config.ELITE_SIGNAL_IMBALANCE_DISTANCE:
            return ("BUY", probability, imbalance) if imbalance == "BUY" else ("SELL", probability, imbalance)

    if imbalance == "BUY" and probability > Config.ELITE_SIGNAL_PROB_THRESHOLD:
        return "BUY", probability, imbalance
    if imbalance == "SELL" and probability < (1 - Config.ELITE_SIGNAL_PROB_THRESHOLD):
        return "SELL", probability, imbalance
    return "HOLD", probability, imbalance


def split_order(bot, pair: str, side: str, total_size: float, bids: list, asks: list) -> list:
    chunks = _safe_chunks()
    size_per_chunk = total_size / chunks
    results = []

    for i in range(chunks):
        if side == "BUY":
            price = _safe_float(asks[i][0]) if i < len(asks) else (_safe_float(asks[-1][0]) if asks else 0)
        else:
            price = _safe_float(bids[i][0]) if i < len(bids) else (_safe_float(bids[-1][0]) if bids else 0)

        if price <= 0:
            bot._logger.warning(f"⚠️ Invalid price for chunk {i} of {pair}")
            continue

        result = execute_single_order(bot, pair, side, price, size_per_chunk)
        if result:
            results.append(result)

    return results


def execute_single_order(bot, pair: str, side: str, price: float, size: float):
    try:
        if Config.AUTO_TRADE_DRY_RUN:
            bot._logger.info(f"[DRY RUN] {side} {pair} {size} @ {price:,.0f}")
            return {"filled": size, "avg_price": price, "status": "simulated"}

        result = bot.indodax.create_order(pair, side.lower(), price, size)
        if result and result.get("success") == 1:
            order_id = result.get("return", {}).get("order_id", "N/A")
            filled = result.get("return", {}).get("receive", size)
            return {"filled": filled, "avg_price": price, "order_id": order_id, "status": "filled"}

        bot._logger.error(f"❌ Order failed for {pair}: {result}")
        return None
    except Exception as e:
        bot._logger.error(f"❌ Order execution error for {pair}: {e}")
        return None


def fee_aware_net_price(price: float, side: str) -> tuple:
    fee = Config.TRADING_FEE_RATE
    if side == "BUY":
        net_entry = price * (1 + fee)
        net_exit = price * (1 - fee)
    else:
        net_entry = price * (1 - fee)
        net_exit = price * (1 + fee)
    return net_entry, net_exit, fee * 2
