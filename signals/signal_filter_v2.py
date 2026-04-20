"""
Enhanced Signal Filter Module V2 (Fixed)
==========================================
Standalone filter system untuk validasi signal sebelum di-eksekusi.
Module ini TIDAK mengganggu bot utama - bisa di-test secara terpisah.

Fixes dari review:
- [FIX 1] Liquidity: tidak reject kalau data tidak ada (skip instead)
- [FIX 2] ATH Distance: logika zombie coin, support large cap bear market
- [FIX 3] Confidence Tiers: validasi konsistensi arah TA vs ML
- [FIX 4] Summary property: hapus hardcode angka filter
- [FIX 5] Tambah cek RSI+Bollinger oversold tidak boleh SELL
- [FIX 6] STRONG_BUY butuh konsensus indikator, bukan hanya angka

Usage:
    from signal_filter_v2 import SignalFilterV2

    f = SignalFilterV2()
    result = f.validate_signal(signal_data, market_data)

    if result.passed:
        print("✅ Signal approved")
    else:
        print(f"❌ Signal rejected: {result.rejection_reasons}")
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Hasil validasi satu filter"""
    filter_name: str
    passed: bool
    reason: str
    severity: str = "INFO"  # INFO, WARNING, CRITICAL
    details: Dict = field(default_factory=dict)


@dataclass
class SignalValidationResult:
    """Hasil validasi signal keseluruhan"""
    signal: Dict
    passed: bool
    timestamp: datetime
    filters_passed: int = 0
    filters_failed: int = 0
    results: List[FilterResult] = field(default_factory=list)
    
    @property
    def rejection_reasons(self) -> List[str]:
        return [r.reason for r in self.results if not r.passed]
    
    @property
    def summary(self) -> str:
        # [FIX 4] Hapus hardcode angka "5" — hitung dinamis dari results
        status = "✅ APPROVED" if self.passed else "❌ REJECTED"
        total = self.filters_passed + self.filters_failed
        return (
            f"{status} | "
            f"Passed: {self.filters_passed}/{total} | "
            f"Failed: {self.filters_failed}/{total}"
        )


class SignalFilterV2:
    """
    Enhanced Signal Filter dengan 6 layer validasi.

    Filters:
    1. Blacklist Check - Cek apakah coin di-blacklist
    2. Liquidity Check - Cek volume 24h minimum
    3. ATH Distance Check - Cek apakah coin sudah "dead" (>80% dari ATH)
    4. Market Cap Check - Cek market cap minimum
    5. Confidence Tier Check - Stricter thresholds untuk BUY/STRONG_BUY
    6. Price Zone Check - Validasi posisi harga vs Support/Resistance (NEW!)
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or self._default_config()
        self.validation_history: List[SignalValidationResult] = []
    
    def _default_config(self) -> Dict:
        return {
            # Filter 1: Blacklist
            "enable_blacklist": False,          # Disabled untuk ML data collection
            "blacklisted_coins": [],            # Isi kalau mau enable

            # Filter 2: Liquidity
            "enable_liquidity_check": True,
            "min_24h_volume_idr": 100_000_000,  # 100 juta IDR minimum
            # Threshold volume untuk dianggap "large cap" (skip ATH check)
            "large_cap_volume_idr": 5_000_000_000,  # 5 miliar IDR

            # Filter 3: ATH Distance
            "enable_ath_check": True,
            "max_ath_distance_pct": 80,         # Skip BUY kalau >80% dari ATH
            "zombie_coin_pct": 95,              # Hard reject kalau >95% dari ATH

            # Filter 4: Market Cap
            "enable_market_cap_check": False,   # Disabled (data sulit didapat)
            "min_market_cap_idr": 1_000_000_000,

            # Filter 5: Confidence Tiers
            "enable_confidence_tiers": True,
            "ml_confidence_min": 0.65,              # Minimum semua rekomendasi
            "ml_confidence_buy": 0.70,              # Minimum untuk BUY
            "ml_confidence_strong_buy": 0.80,       # Minimum untuk STRONG_BUY
            "combined_strength_buy": 0.30,          # Minimum strength untuk BUY
            "combined_strength_strong_buy": 0.60,   # Minimum strength untuk STRONG_BUY
            # Maksimum indikator bearish yang boleh ada di STRONG_BUY
            "max_bearish_indicators_strong_buy": 1,
        }
    
    def validate_signal(
        self,
        signal: Dict,
        market_data: Optional[Dict] = None
    ) -> SignalValidationResult:
        """
        Validate signal through all 5 filters.
        
        Args:
            signal: Signal data dari bot (pair, recommendation, ml_confidence, dll)
            market_data: Data tambahan (volume, ath, market_cap, dll)
            
        Returns:
            SignalValidationResult dengan detail semua filter
        """
        results = []
        
        # Run all filters
        results.append(self._check_blacklist(signal))
        results.append(self._check_liquidity(signal, market_data or {}))
        results.append(self._check_ath_distance(signal, market_data or {}))
        results.append(self._check_market_cap(signal, market_data or {}))
        results.append(self._check_confidence_tiers(signal))
        results.append(self._check_price_zone(signal))  # NEW: Filter 6 - S/R validation
        
        # Calculate summary
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        
        validation = SignalValidationResult(
            signal=signal,
            passed=failed == 0,  # ALL filters must pass
            timestamp=datetime.now(),
            filters_passed=passed,
            filters_failed=failed,
            results=results
        )
        
        # Save to history
        self.validation_history.append(validation)
        
        # Log result
        self._log_validation(validation)
        
        return validation
    
    def _check_blacklist(self, signal: Dict) -> FilterResult:
        """Filter 1: Cek apakah coin di-blacklist"""
        if not self.config["enable_blacklist"]:
            return FilterResult("Blacklist", True, "Filter disabled")
        
        pair = signal.get("pair", "").lower()
        symbol = pair.replace("idr", "").lower()
        
        for blacklisted in self.config["blacklisted_coins"]:
            if symbol in blacklisted.lower() or blacklisted.lower() in symbol:
                return FilterResult(
                    filter_name="Blacklist",
                    passed=False,
                    reason=f"Coin blacklisted: {pair}",
                    severity="CRITICAL",
                    details={"blacklisted_match": blacklisted}
                )
        
        return FilterResult("Blacklist", True, "Coin not in blacklist")
    
    def _check_liquidity(
        self,
        signal: Dict,
        market_data: Dict
    ) -> FilterResult:
        """
        Filter 2: Cek volume 24h minimum.
        
        [FIX 1] Kalau data tidak ada → skip filter (passed=True + WARNING),
        bukan langsung reject. Reject hanya kalau data ada tapi memang rendah.
        """
        if not self.config["enable_liquidity_check"]:
            return FilterResult("Liquidity", True, "Filter disabled")

        volume_idr = market_data.get("volume_24h_idr", None)
        min_volume = self.config["min_24h_volume_idr"]

        # [FIX 1] Data tidak ada → skip, bukan reject
        if volume_idr is None or volume_idr == 0:
            return FilterResult(
                filter_name="Liquidity",
                passed=True,
                reason=f"Data volume tidak tersedia untuk {signal.get('pair', '?').upper()} — filter dilewati",
                severity="WARNING",
                details={"note": "Pertimbangkan menyediakan market_data untuk hasil lebih akurat"},
            )

        if volume_idr < min_volume:
            shortfall = (1 - volume_idr / min_volume) * 100
            return FilterResult(
                filter_name="Liquidity",
                passed=False,
                reason=f"Volume terlalu rendah: {volume_idr:,.0f} IDR (min: {min_volume:,.0f} IDR, kurang {shortfall:.1f}%)",
                severity="CRITICAL",
                details={
                    "volume_idr": volume_idr,
                    "min_required": min_volume,
                    "shortfall_pct": shortfall,
                },
            )

        return FilterResult(
            "Liquidity",
            True,
            f"Volume OK: {volume_idr:,.0f} IDR",
        )
    
    def _check_ath_distance(
        self,
        signal: Dict,
        market_data: Dict
    ) -> FilterResult:
        """
        Filter 3: Cek apakah coin sudah 'mati' (terlalu jauh dari ATH).
        
        [FIX 2] Perbaikan logika:
        - Data tidak ada → skip (bukan reject)
        - Zombie coin (>95% dari ATH) → hard reject BUY
        - Dead coin (>80% dari ATH) → reject BUY kecuali large cap
        - Coin baru ATH (distance negatif) → pass dengan catatan
        - SELL/HOLD tidak terpengaruh filter ini
        """
        if not self.config["enable_ath_check"]:
            return FilterResult("ATH Distance", True, "Filter disabled")

        current_price = signal.get("price", 0)
        ath_price = market_data.get("ath_price", 0)
        recommendation = signal.get("recommendation", "HOLD")
        volume_idr = market_data.get("volume_24h_idr", 0)

        # [FIX 2a] Data tidak ada → skip
        if ath_price == 0 or current_price == 0:
            return FilterResult(
                filter_name="ATH Distance",
                passed=True,
                reason=f"Data ATH tidak tersedia untuk {signal.get('pair', '?').upper()} — filter dilewati",
                severity="WARNING",
            )

        distance_pct = (1 - current_price / ath_price) * 100
        is_buy_signal = recommendation in ["BUY", "STRONG_BUY"]
        zombie_threshold = self.config["zombie_coin_pct"]
        dead_threshold = self.config["max_ath_distance_pct"]
        large_cap_volume = self.config["large_cap_volume_idr"]

        # [FIX 2b] Coin baru ATH (harga di atas ATH lama) → pass dengan info
        if distance_pct < 0:
            return FilterResult(
                filter_name="ATH Distance",
                passed=True,
                reason=f"Coin di atas ATH sebelumnya: +{abs(distance_pct):.1f}% (hati-hati overbought)",
                severity="WARNING",
                details={"distance_pct": distance_pct},
            )

        # [FIX 2c] Zombie coin (>95% dari ATH) → selalu reject BUY
        if distance_pct >= zombie_threshold and is_buy_signal:
            return FilterResult(
                filter_name="ATH Distance",
                passed=False,
                reason=f"Zombie coin: -{distance_pct:.1f}% dari ATH (threshold: {zombie_threshold}%) — terlalu berisiko untuk BUY",
                severity="CRITICAL",
                details={
                    "current_price": current_price,
                    "ath_price": ath_price,
                    "distance_pct": distance_pct,
                },
            )

        # [FIX 2d] Dead coin (>80% dari ATH) → reject BUY kecuali large cap
        if distance_pct >= dead_threshold and is_buy_signal:
            if volume_idr >= large_cap_volume:
                return FilterResult(
                    filter_name="ATH Distance",
                    passed=True,
                    reason=f"Jauh dari ATH (-{distance_pct:.1f}%) tapi large cap (volume {volume_idr:,.0f} IDR) — diizinkan",
                    severity="WARNING",
                    details={"distance_pct": distance_pct},
                )
            return FilterResult(
                filter_name="ATH Distance",
                passed=False,
                reason=f"Coin terlalu jauh dari ATH: -{distance_pct:.1f}% (max: {dead_threshold}%) dan bukan large cap",
                severity="WARNING",
                details={
                    "current_price": current_price,
                    "ath_price": ath_price,
                    "distance_pct": distance_pct,
                },
            )

        return FilterResult(
            "ATH Distance",
            True,
            f"ATH distance OK: -{distance_pct:.1f}%",
        )
    
    def _check_market_cap(
        self,
        signal: Dict,
        market_data: Dict
    ) -> FilterResult:
        """Filter 4: Cek market cap minimum."""
        if not self.config["enable_market_cap_check"]:
            return FilterResult("Market Cap", True, "Filter disabled")

        market_cap = market_data.get("market_cap_idr", None)
        min_cap = self.config["min_market_cap_idr"]

        # Data tidak ada → skip
        if market_cap is None or market_cap == 0:
            return FilterResult(
                filter_name="Market Cap",
                passed=True,
                reason=f"Data market cap tidak tersedia untuk {signal.get('pair', '?').upper()} — filter dilewati",
                severity="WARNING",
            )

        if market_cap < min_cap:
            return FilterResult(
                filter_name="Market Cap",
                passed=False,
                reason=f"Market cap terlalu kecil: {market_cap:,.0f} IDR (min: {min_cap:,.0f} IDR)",
                severity="CRITICAL",
                details={"market_cap_idr": market_cap, "min_required": min_cap},
            )

        return FilterResult(
            "Market Cap",
            True,
            f"Market cap OK: {market_cap:,.0f} IDR",
        )
    
    def _check_confidence_tiers(self, signal: Dict) -> FilterResult:
        """
        Filter 5: Validasi confidence + konsistensi arah sinyal.
        
        [FIX 3] Perbaikan utama:
        - BUY/STRONG_BUY tidak boleh punya combined_strength negatif
        - SELL/STRONG_SELL tidak boleh punya combined_strength positif tinggi
        - STRONG_BUY butuh konsensus indikator (maks 1 indikator bearish)
        - RSI+Bollinger oversold → tidak boleh SELL (potensi jual di bottom)
        - Threshold konsisten
        """
        if not self.config["enable_confidence_tiers"]:
            return FilterResult("Confidence Tiers", True, "Filter disabled")

        recommendation = signal.get("recommendation", "HOLD")
        ml_confidence = signal.get("ml_confidence", 0)
        combined_strength = signal.get("combined_strength", 0)
        rsi = signal.get("rsi", "NEUTRAL")
        macd = signal.get("macd", "NEUTRAL")
        ma_trend = signal.get("ma_trend", "NEUTRAL")
        bollinger = signal.get("bollinger", "NEUTRAL")

        min_conf = self.config["ml_confidence_min"]

        # --- Cek 1: Minimum ML confidence (berlaku untuk semua) ---
        if ml_confidence < min_conf:
            return FilterResult(
                filter_name="Confidence Tiers",
                passed=False,
                reason=f"ML confidence terlalu rendah: {ml_confidence:.1%} < {min_conf:.0%}",
                severity="CRITICAL",
                details={"ml_confidence": ml_confidence, "min_required": min_conf},
            )

        # --- Cek 2: Arah ML vs TA harus searah untuk BUY ---
        # [FIX 3a] combined_strength negatif + BUY = konflik sinyal
        if recommendation in ["BUY", "STRONG_BUY"] and combined_strength < 0:
            return FilterResult(
                filter_name="Confidence Tiers",
                passed=False,
                reason=(
                    f"Konflik sinyal: {recommendation} tapi combined_strength negatif "
                    f"({combined_strength:.2f}) — TA dan ML berlawanan arah"
                ),
                severity="CRITICAL",
                details={"combined_strength": combined_strength, "recommendation": recommendation},
            )

        # [FIX 3b] combined_strength positif tinggi + SELL = konflik sinyal
        if recommendation in ["SELL", "STRONG_SELL"] and combined_strength > 0.3:
            return FilterResult(
                filter_name="Confidence Tiers",
                passed=False,
                reason=(
                    f"Konflik sinyal: {recommendation} tapi combined_strength positif "
                    f"({combined_strength:.2f}) — pertimbangkan HOLD"
                ),
                severity="WARNING",
                details={"combined_strength": combined_strength},
            )

        # [FIX 5] RSI + Bollinger keduanya OVERSOLD → jangan SELL (potensi jual di bottom)
        if recommendation in ["SELL", "STRONG_SELL"]:
            if rsi == "OVERSOLD" and bollinger == "OVERSOLD":
                return FilterResult(
                    filter_name="Confidence Tiers",
                    passed=False,
                    reason=(
                        f"Bahaya jual di bottom: RSI OVERSOLD + Bollinger OVERSOLD "
                        f"tapi rekomendasi {recommendation} — tunggu konfirmasi"
                    ),
                    severity="CRITICAL",
                    details={"rsi": rsi, "bollinger": bollinger},
                )

        # --- Cek 3: STRONG_BUY — butuh konsensus indikator ---
        if recommendation == "STRONG_BUY":
            # [FIX 6] Hitung berapa indikator bearish
            bearish_indicators = []
            if macd in ["BEARISH", "BEARISH_CROSS"]:
                bearish_indicators.append(f"MACD={macd}")
            if ma_trend == "BEARISH":
                bearish_indicators.append(f"MA={ma_trend}")
            if rsi == "OVERBOUGHT":
                bearish_indicators.append(f"RSI={rsi}")

            max_bearish = self.config["max_bearish_indicators_strong_buy"]
            if len(bearish_indicators) > max_bearish:
                return FilterResult(
                    filter_name="Confidence Tiers",
                    passed=False,
                    reason=(
                        f"STRONG_BUY tidak valid: {len(bearish_indicators)} indikator bearish "
                        f"({', '.join(bearish_indicators)}) — turunkan ke BUY atau HOLD"
                    ),
                    severity="WARNING",
                    details={"bearish_indicators": bearish_indicators},
                )

            # Threshold strength dan ML untuk STRONG_BUY
            req_strength = self.config["combined_strength_strong_buy"]
            req_ml = self.config["ml_confidence_strong_buy"]

            if combined_strength < req_strength:
                return FilterResult(
                    filter_name="Confidence Tiers",
                    passed=False,
                    reason=f"STRONG_BUY butuh combined_strength ≥ {req_strength}, dapat {combined_strength:.2f}",
                    severity="WARNING",
                    details={"combined_strength": combined_strength, "required": req_strength},
                )

            if ml_confidence < req_ml:
                return FilterResult(
                    filter_name="Confidence Tiers",
                    passed=False,
                    reason=f"STRONG_BUY butuh ML ≥ {req_ml:.0%}, dapat {ml_confidence:.1%}",
                    severity="WARNING",
                    details={"ml_confidence": ml_confidence, "required": req_ml},
                )

        # --- Cek 4: BUY biasa ---
        elif recommendation == "BUY":
            req_strength = self.config["combined_strength_buy"]
            req_ml = self.config["ml_confidence_buy"]

            if combined_strength < req_strength:
                return FilterResult(
                    filter_name="Confidence Tiers",
                    passed=False,
                    reason=f"BUY butuh combined_strength ≥ {req_strength}, dapat {combined_strength:.2f}",
                    severity="WARNING",
                    details={"combined_strength": combined_strength, "required": req_strength},
                )

            if ml_confidence < req_ml:
                return FilterResult(
                    filter_name="Confidence Tiers",
                    passed=False,
                    reason=f"BUY butuh ML ≥ {req_ml:.0%}, dapat {ml_confidence:.1%}",
                    severity="WARNING",
                    details={"ml_confidence": ml_confidence, "required": req_ml},
                )

        return FilterResult(
            "Confidence Tiers",
            True,
            f"Semua confidence OK: ML={ml_confidence:.1%}, Strength={combined_strength:.2f}",
        )
    
    # ------------------------------------------------------------------
    # Filter 6: Price Zone (Support/Resistance validation)
    # ------------------------------------------------------------------

    def _check_price_zone(self, signal: Dict) -> FilterResult:
        """
        Filter 6: Validasi posisi harga terhadap Support/Resistance.
        
        Aturan:
        - Jangan BUY kalau harga sudah di zona resistance
        - Jangan SELL kalau harga sudah di zona support
        - Hitung risk/reward — tolak kalau < 1.5
        """
        price = signal.get("price", 0)
        recommendation = signal.get("recommendation", "HOLD")
        support_1 = signal.get("support_1", 0)
        support_2 = signal.get("support_2", 0)
        resistance_1 = signal.get("resistance_1", 0)
        resistance_2 = signal.get("resistance_2", 0)

        # Kalau tidak ada data S/R → skip filter
        if support_1 == 0 or resistance_1 == 0:
            return FilterResult(
                "Price Zone", True,
                "Data S/R tidak tersedia — filter dilewati",
                severity="WARNING"
            )

        # Hitung jarak ke S/R (dalam %)
        distance_to_support = ((price - support_1) / price) * 100 if price > 0 else 0
        distance_to_resistance = ((resistance_1 - price) / price) * 100 if price > 0 else 0

        # Risk/Reward ratio
        risk = price - support_1      # berapa rugi kalau salah
        reward = resistance_1 - price # berapa untung kalau benar
        rr_ratio = reward / risk if risk > 0 else 0

        # === Aturan BUY ===
        if recommendation in ["BUY", "STRONG_BUY"]:

            # Jangan BUY kalau harga sudah di dekat/atas resistance
            if distance_to_resistance < 2:
                return FilterResult(
                    filter_name="Price Zone",
                    passed=False,
                    reason=f"BUY terlalu dekat resistance: harga {price:,.0f} vs R1 {resistance_1:,.0f} (jarak {distance_to_resistance:.1f}%)",
                    severity="WARNING"
                )

            # Tolak kalau Risk/Reward jelek
            if rr_ratio < 1.5:
                return FilterResult(
                    filter_name="Price Zone",
                    passed=False,
                    reason=f"Risk/Reward terlalu rendah: {rr_ratio:.2f} (min 1.5) — potensi profit tidak sebanding risiko",
                    severity="WARNING",
                    details={"risk": risk, "reward": reward, "rr_ratio": rr_ratio}
                )

            # Harga sudah di bawah support — berbahaya
            if support_2 > 0 and price < support_2:
                return FilterResult(
                    filter_name="Price Zone",
                    passed=False,
                    reason=f"Harga {price:,.0f} di bawah support kuat {support_2:,.0f} — tren sangat bearish",
                    severity="CRITICAL"
                )

        # === Aturan SELL ===
        if recommendation in ["SELL", "STRONG_SELL"]:

            # Jangan SELL kalau harga sudah di dekat support
            if distance_to_support < 2:
                return FilterResult(
                    filter_name="Price Zone",
                    passed=False,
                    reason=f"SELL terlalu dekat support: harga {price:,.0f} vs S1 {support_1:,.0f} (jarak {distance_to_support:.1f}%) — potensi jual di bottom",
                    severity="WARNING"
                )

        return FilterResult(
            "Price Zone",
            True,
            f"Posisi harga OK | S1:{support_1:,.0f} ← [{price:,.0f}] → R1:{resistance_1:,.0f} | R/R: {rr_ratio:.2f}",
            details={"rr_ratio": rr_ratio, "dist_support": distance_to_support,
                     "dist_resistance": distance_to_resistance}
        )

    # ------------------------------------------------------------------
    # Logging & Reporting
    # ------------------------------------------------------------------

    def _log_validation(self, result: SignalValidationResult):
        """Log validation result"""
        pair = result.signal.get("pair", "Unknown").upper()
        rec = result.signal.get("recommendation", "Unknown")
        
        if result.passed:
            logger.info(f"✅ {pair} - {rec} | {result.summary}")
        else:
            reasons = "; ".join(result.rejection_reasons)
            logger.warning(f"❌ {pair} - {rec} REJECTED | {result.summary} | {reasons}")

    def get_validation_report(self) -> str:
        """Generate laporan dari semua validation history."""
        if not self.validation_history:
            return "Belum ada validasi yang dilakukan."

        total = len(self.validation_history)
        approved = sum(1 for v in self.validation_history if v.passed)
        rejected = total - approved

        lines = [
            "=" * 60,
            "  SIGNAL FILTER V2 — VALIDATION REPORT",
            "=" * 60,
            f"Total Validasi : {total}",
            f"Approved       : {approved} ({approved / total * 100:.1f}%)",
            f"Rejected       : {rejected} ({rejected / total * 100:.1f}%)",
            "",
        ]

        # Breakdown per filter
        filter_stats: Dict[str, Dict] = {}
        for v in self.validation_history:
            for r in v.results:
                s = filter_stats.setdefault(r.filter_name, {"passed": 0, "failed": 0})
                if r.passed:
                    s["passed"] += 1
                else:
                    s["failed"] += 1

        lines.append("Breakdown per Filter:")
        for fname, stats in filter_stats.items():
            total_f = stats["passed"] + stats["failed"]
            pass_rate = stats["passed"] / total_f * 100 if total_f > 0 else 0
            icon = "✅" if stats["failed"] == 0 else ("⚠️" if pass_rate >= 50 else "🛑")
            lines.append(
                f"  {icon} {fname}: {stats['passed']}/{total_f} lolos ({pass_rate:.0f}%)"
            )

        lines.append("")
        lines.append("10 Validasi Terakhir:")
        for v in self.validation_history[-10:]:
            status = "✅" if v.passed else "❌"
            pair = v.signal.get("pair", "?").upper()
            rec = v.signal.get("recommendation", "?")
            lines.append(f"  {status} {pair} - {rec} | {v.summary}")

        lines.append("=" * 60)
        return "\n".join(lines)


# Quick self-test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    f = SignalFilterV2()

    test_cases = [
        # (label, signal, market_data)
        (
            "RFCIDR STRONG_BUY — zombie coin + low volume",
            {"pair": "rfcidr", "recommendation": "STRONG_BUY", "price": 9.39,
             "ml_confidence": 0.726, "combined_strength": 0.78,
             "rsi": "NEUTRAL", "macd": "BULLISH", "ma_trend": "BULLISH", "bollinger": "NEUTRAL"},
            {"volume_24h_idr": 52_500_000, "ath_price": 2_100_000, "market_cap_idr": 600_000_000},
        ),
        (
            "PIPPINIDR BUY — TA negatif vs ML tinggi (konflik sinyal)",
            {"pair": "pippinidr", "recommendation": "BUY", "price": 517.035,
             "ml_confidence": 0.951, "combined_strength": -0.20,
             "rsi": "OVERSOLD", "macd": "BEARISH", "ma_trend": "BEARISH", "bollinger": "NEUTRAL"},
            {"volume_24h_idr": 150_000_000, "ath_price": 2_500, "market_cap_idr": 5_000_000_000},
        ),
        (
            "BTCIDR BUY — large cap, volume besar",
            {"pair": "btcidr", "recommendation": "BUY", "price": 1_237_992_000,
             "ml_confidence": 0.75, "combined_strength": 0.45,
             "rsi": "OVERSOLD", "macd": "BULLISH", "ma_trend": "BULLISH", "bollinger": "NEUTRAL"},
            {"volume_24h_idr": 8_000_000_000, "ath_price": 1_500_000_000, "market_cap_idr": 500_000_000_000},
        ),
        (
            "ETHIDR STRONG_BUY — semua bagus",
            {"pair": "ethidr", "recommendation": "STRONG_BUY", "price": 37_997_000,
             "ml_confidence": 0.85, "combined_strength": 0.88,
             "rsi": "OVERSOLD", "macd": "BULLISH", "ma_trend": "BULLISH", "bollinger": "NEUTRAL"},
            {"volume_24h_idr": 3_000_000_000, "ath_price": 65_000_000, "market_cap_idr": 200_000_000_000},
        ),
        (
            "SELL saat RSI+Bollinger OVERSOLD — bahaya jual di bottom",
            {"pair": "solidr", "recommendation": "SELL", "price": 245_000,
             "ml_confidence": 0.87, "combined_strength": -0.28,
             "rsi": "OVERSOLD", "macd": "BEARISH", "ma_trend": "BEARISH", "bollinger": "OVERSOLD"},
            {"volume_24h_idr": 800_000_000, "ath_price": 350_000, "market_cap_idr": 15_000_000_000},
        ),
    ]

    print("\n" + "=" * 70)
    print("  SIGNAL FILTER V2 — TEST SUITE")
    print("=" * 70)

    for label, signal, market in test_cases:
        print(f"\n🧪 Test: {label}")
        print("-" * 70)
        result = f.validate_signal(signal, market)
        
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"Result: {status}")
        print(f"Summary: {result.summary}")
        
        if not result.passed:
            print("\nRejection Reasons:")
            for reason in result.rejection_reasons:
                print(f"  • {reason}")
        
        print("\nFilter Details:")
        for r in result.results:
            icon = "  ✅" if r.passed else "  ❌"
            severity_tag = f" [{r.severity}]" if r.severity not in ("INFO",) and not r.passed else ""
            print(f"{icon} {r.filter_name}:{severity_tag} {r.reason}")

    print("\n" + "=" * 70)
    print(f.get_validation_report())
