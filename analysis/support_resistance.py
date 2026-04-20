#!/usr/bin/env python3
"""
Support & Resistance Level Detection
=====================================
Auto-detect support and resistance levels from historical price data.

Features:
- Multiple detection methods (local minima/maxima, pivot points, volume clusters)
- Dynamic level updates (recalculates with new candles)
- Price zone classification (SUPPORT, RESISTANCE, MIDDLE, BREAKOUT)
- Risk/Reward ratio calculation
- Trendline detection (descending/ascending channels)

Usage:
    from support_resistance import SupportResistanceDetector
    
    detector = SupportResistanceDetector()
    sr_levels = detector.detect_levels(df, levels=2)
    
    # Result:
    # {
    #     'support_1': 1650, 'support_2': 1562,
    #     'resistance_1': 1777, 'resistance_2': 1866,
    #     'price_zone': 'MIDDLE',
    #     'risk_reward_ratio': 2.1,
    #     ...
    # }
"""

import numpy as np
import pandas as pd
import logging
import json
import os
from typing import Dict, Optional, Tuple
from scipy.signal import argrelextrema

logger = logging.getLogger('crypto_bot')

MANUAL_SR_FILE = "manual_sr_levels.json"


class SupportResistanceDetector:
    """
    Detect support and resistance levels from historical OHLCV data.
    
    Methods:
    1. Local Minima/Maxima (scipy argrelextrema)
    2. Pivot Points (standard formula)
    3. Volume-weighted price clusters
    4. Recent swing highs/lows
    """

    def __init__(self):
        logger.info("✅ Support & Resistance Detector initialized")
        self.manual_levels = self._load_manual_levels()

    def _load_manual_levels(self) -> Dict:
        """Load manual S/R levels from JSON file."""
        if not os.path.exists(MANUAL_SR_FILE):
            logger.debug(f"⚠️ Manual S/R file not found: {MANUAL_SR_FILE}")
            return {}
        
        try:
            with open(MANUAL_SR_FILE, 'r') as f:
                data = json.load(f)
            levels = data.get('levels', {})
            if levels:
                logger.info(f"✅ Loaded manual S/R levels for {len(levels)} pairs")
            return levels
        except Exception as e:
            logger.error(f"❌ Failed to load manual S/R levels: {e}")
            return {}

    def save_manual_levels(self, levels: Dict) -> bool:
        """Save manual S/R levels to JSON file."""
        try:
            data = {
                "_comment": "Manual Support/Resistance Levels - Override auto-detection",
                "levels": levels
            }
            with open(MANUAL_SR_FILE, 'w') as f:
                json.dump(data, f, indent=4)
            self.manual_levels = levels
            logger.info(f"✅ Saved manual S/R levels for {len(levels)} pairs")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save manual S/R levels: {e}")
            return False

    def set_manual_levels(self, pair: str, s1: float, s2: float, r1: float, r2: float, notes: str = "") -> bool:
        """Set manual S/R levels for a specific pair."""
        pair_lower = pair.lower()
        self.manual_levels[pair_lower] = {
            "support_1": s1,
            "support_2": s2,
            "resistance_1": r1,
            "resistance_2": r2,
            "notes": notes
        }
        return self.save_manual_levels(self.manual_levels)

    def get_manual_levels(self, pair: str) -> Optional[Dict]:
        """Get manual S/R levels for a pair if they exist."""
        pair_lower = pair.lower()
        if pair_lower in self.manual_levels:
            levels = self.manual_levels[pair_lower]
            return {
                'support_1': levels['support_1'],
                'support_2': levels['support_2'],
                'resistance_1': levels['resistance_1'],
                'resistance_2': levels['resistance_2'],
                'price_zone': 'MANUAL',
                'risk_reward_ratio': 0,
                'distance_to_support_pct': 0,
                'distance_to_resistance_pct': 0,
                'detection_method': 'manual_override',
                'notes': levels.get('notes', '')
            }
        return None

    def detect_levels(
        self,
        df: pd.DataFrame,
        levels: int = 2,
        current_price: float = None,
        method: str = 'auto',
        pair: str = None
    ) -> Dict:
        """
        Detect support and resistance levels from historical data.
        
        PRIORITY: Manual override > Auto-detection
        
        Args:
            df: DataFrame with columns ['high', 'low', 'close', 'volume']
            levels: Number of S/R levels to detect (default: 2)
            current_price: Current price for zone classification
            method: 'local_extrema' | 'pivot' | 'volume' | 'swing' | 'auto'
            pair: Pair name to check for manual override

        Returns:
            Dict with support/resistance levels and metadata
        """
        # CHECK 1: Manual override first
        if pair:
            manual = self.get_manual_levels(pair)
            if manual:
                # Calculate derived metrics for manual levels
                if current_price is None:
                    current_price = df['close'].iloc[-1] if not df.empty else 0
                manual = self._calculate_derived_metrics(manual, current_price)
                manual['price_zone'] = self._classify_price_zone(
                    current_price,
                    manual.get('support_1', 0),
                    manual.get('resistance_1', 0)
                )
                logger.info(
                    f"📝 [MANUAL S/R] {pair}: Using manual override | "
                    f"S1={manual['support_1']:,.0f} R1={manual['resistance_1']:,.0f}"
                )
                return manual

        # CHECK 2: Auto-detect
        if df.empty or len(df) < 20:
            logger.warning("⚠️ Not enough data for S/R detection (need 20+ candles)")
            return self._empty_result()

        if current_price is None:
            current_price = df['close'].iloc[-1]

        # Auto-select best method based on data characteristics
        if method == 'auto':
            if len(df) >= 100:
                method = 'local_extrema'  # Most accurate with lots of data
            elif 'volume' in df.columns and df['volume'].sum() > 0:
                method = 'volume'  # Good with volume data
            else:
                method = 'swing'  # Fallback for small datasets

        logger.info(f"📊 Detecting S/R levels using method: {method}")

        # Detect levels using selected method
        if method == 'local_extrema':
            result = self._detect_local_extrema(df, levels, current_price)
        elif method == 'pivot':
            result = self._detect_pivot_points(df, current_price)
        elif method == 'volume':
            result = self._detect_volume_clusters(df, levels, current_price)
        elif method == 'swing':
            result = self._detect_swing_points(df, levels, current_price)
        else:
            result = self._detect_local_extrema(df, levels, current_price)

        # Calculate derived metrics
        result = self._calculate_derived_metrics(result, current_price)
        
        # Classify price zone
        result['price_zone'] = self._classify_price_zone(
            current_price, 
            result.get('support_1', 0), 
            result.get('resistance_1', 0)
        )

        return result

    def _detect_local_extrema(
        self, 
        df: pd.DataFrame, 
        levels: int, 
        current_price: float
    ) -> Dict:
        """
        Method 1: Local Minima/Maxima using scipy argrelextrema.
        Best for: Large datasets (100+ candles)
        """
        order = max(5, len(df) // 20)  # Adaptive order based on data length
        
        # Find local minima (supports)
        lows = argrelextrema(df['low'].values, np.less, order=order)[0]
        # Find local maxima (resistances)
        highs = argrelextrema(df['high'].values, np.greater, order=order)[0]
        
        # Extract price levels
        support_levels = sorted([df['low'].iloc[i] for i in lows if df['low'].iloc[i] < current_price], reverse=True)
        resistance_levels = sorted([df['high'].iloc[i] for i in highs if df['high'].iloc[i] > current_price])
        
        # If not enough levels, use recent swing points
        if len(support_levels) < levels:
            recent_lows = sorted(df['low'].tail(50).tolist(), reverse=True)
            support_levels.extend([l for l in recent_lows if l < current_price][:levels - len(support_levels)])
            
        if len(resistance_levels) < levels:
            recent_highs = sorted(df['high'].tail(50).tolist())
            resistance_levels.extend([h for h in recent_highs if h > current_price][:levels - len(resistance_levels)])
        
        return {
            'support_1': support_levels[0] if len(support_levels) > 0 else current_price * 0.98,
            'support_2': support_levels[1] if len(support_levels) > 1 else current_price * 0.96,
            'resistance_1': resistance_levels[0] if len(resistance_levels) > 0 else current_price * 1.02,
            'resistance_2': resistance_levels[1] if len(resistance_levels) > 1 else current_price * 1.04,
            'detection_method': 'local_extrema',
            'levels_found': {'support': len(support_levels), 'resistance': len(resistance_levels)}
        }

    def _detect_pivot_points(self, df: pd.DataFrame, current_price: float) -> Dict:
        """
        Method 2: Standard Pivot Points (H+L+C)/3 based.
        Best for: Quick calculation with limited data
        """
        last_candle = df.iloc[-1]
        high = last_candle['high']
        low = last_candle['low']
        close = last_candle['close']
        
        pivot = (high + low + close) / 3
        
        support_1 = (2 * pivot) - high
        support_2 = pivot - (high - low)
        resistance_1 = (2 * pivot) - low
        resistance_2 = pivot + (high - low)
        
        return {
            'support_1': support_1,
            'support_2': support_2,
            'resistance_1': resistance_1,
            'resistance_2': resistance_2,
            'pivot': pivot,
            'detection_method': 'pivot_points'
        }

    def _detect_volume_clusters(
        self, 
        df: pd.DataFrame, 
        levels: int, 
        current_price: float
    ) -> Dict:
        """
        Method 3: Volume-weighted price clusters.
        Best for: Finding high-volume trading zones
        """
        if 'volume' not in df.columns or df['volume'].sum() == 0:
            return self._detect_swing_points(df, levels, current_price)
        
        # Create price bins
        price_range = df['high'].max() - df['low'].min()
        bin_size = price_range / 50  # 50 bins
        bins = np.arange(df['low'].min(), df['high'].max() + bin_size, bin_size)
        
        # Calculate volume per price bin
        volume_by_price = np.zeros(len(bins) - 1)
        for i in range(len(bins) - 1):
            mask = (df['close'] >= bins[i]) & (df['close'] < bins[i + 1])
            volume_by_price[i] = df.loc[mask, 'volume'].sum()
        
        # Find high-volume clusters
        high_volume_threshold = np.percentile(volume_by_price, 80)
        high_volume_bins = np.where(volume_by_price >= high_volume_threshold)[0]
        
        # Separate into support (below price) and resistance (above price)
        support_bins = [b for b in high_volume_bins if bins[b] < current_price]
        resistance_bins = [b for b in high_volume_bins if bins[b] > current_price]
        
        # Get top levels
        support_levels = sorted([bins[b] for b in support_bins], reverse=True)[:levels]
        resistance_levels = sorted([bins[b] for b in resistance_bins])[:levels]
        
        return {
            'support_1': support_levels[0] if len(support_levels) > 0 else current_price * 0.98,
            'support_2': support_levels[1] if len(support_levels) > 1 else current_price * 0.96,
            'resistance_1': resistance_levels[0] if len(resistance_levels) > 0 else current_price * 1.02,
            'resistance_2': resistance_levels[1] if len(resistance_levels) > 1 else current_price * 1.04,
            'detection_method': 'volume_clusters'
        }

    def _detect_swing_points(
        self,
        df: pd.DataFrame,
        levels: int,
        current_price: float
    ) -> Dict:
        """
        Method 4: Swing High/Low dengan clustering dan touch counting.
        
        Ini adalah pendekatan paling canggih:
        1. Deteksi swing high/low menggunakan window
        2. Cluster level yang berdekatan (dalam 1%)
        3. Hitung berapa kali harga menyentuh level (touches)
        4. Filter hanya yang kuat (min 2 touches)
        
        Best for: Semua timeframe, menghasilkan level yang kuat
        """
        window = max(5, len(df) // 20)  # Window dinamis berdasarkan data
        min_touches = 2  # Minimal 2 sentuhan untuk level kuat
        
        raw_levels = []
        
        # Deteksi swing high/low
        for i in range(window, len(df) - window):
            # Swing High = candle tertinggi dalam window
            is_swing_high = (
                df["high"].iloc[i] == df["high"].iloc[i-window:i+window+1].max()
            )
            # Swing Low = candle terendah dalam window
            is_swing_low = (
                df["low"].iloc[i] == df["low"].iloc[i-window:i+window+1].min()
            )
            
            if is_swing_high:
                raw_levels.append(("resistance", float(df["high"].iloc[i])))
            if is_swing_low:
                raw_levels.append(("support", float(df["low"].iloc[i])))
        
        # Cluster nearby levels (dalam 1%)
        clustered = self._cluster_nearby_levels(raw_levels, tolerance_pct=0.01)
        
        # Filter level yang kuat (min touches)
        strong_levels = [lvl for lvl in clustered if lvl["touches"] >= min_touches]
        
        # Separate support dan resistance
        support_levels = sorted(
            [lvl for lvl in strong_levels if lvl["type"] == "support" and lvl["price"] < current_price],
            key=lambda x: x["price"],
            reverse=True  # Yang terdekat dengan harga dulu
        )
        
        resistance_levels = sorted(
            [lvl for lvl in strong_levels if lvl["type"] == "resistance" and lvl["price"] > current_price],
            key=lambda x: x["price"]  # Yang terdekat dengan harga dulu
        )
        
        # Fallback kalau tidak cukup level kuat
        if len(support_levels) < levels:
            # Gunakan semua swing lows yang ada
            all_lows = sorted([lvl for lvl in clustered if lvl["type"] == "support" and lvl["price"] < current_price], 
                             key=lambda x: x["price"], reverse=True)
            support_levels.extend(all_lows[levels - len(support_levels):])
            
        if len(resistance_levels) < levels:
            all_highs = sorted([lvl for lvl in clustered if lvl["type"] == "resistance" and lvl["price"] > current_price],
                              key=lambda x: x["price"])
            resistance_levels.extend(all_highs[levels - len(resistance_levels):])
        
        # Final fallback dengan harga ekstrem
        if len(support_levels) < levels:
            min_price = df['low'].min()
            while len(support_levels) < levels:
                support_levels.append({"price": min_price * (1 - 0.02 * len(support_levels)), "touches": 1})
                
        if len(resistance_levels) < levels:
            max_price = df['high'].max()
            while len(resistance_levels) < levels:
                resistance_levels.append({"price": max_price * (1 + 0.02 * len(resistance_levels)), "touches": 1})
        
        return {
            'support_1': support_levels[0]["price"] if len(support_levels) > 0 else current_price * 0.98,
            'support_2': support_levels[1]["price"] if len(support_levels) > 1 else current_price * 0.96,
            'resistance_1': resistance_levels[0]["price"] if len(resistance_levels) > 0 else current_price * 1.02,
            'resistance_2': resistance_levels[1]["price"] if len(resistance_levels) > 1 else current_price * 1.04,
            'detection_method': 'swing_clustered',
            'sr_details': {
                's1_touches': support_levels[0].get('touches', 0) if support_levels else 0,
                'r1_touches': resistance_levels[0].get('touches', 0) if resistance_levels else 0
            }
        }

    def _cluster_nearby_levels(self, levels: list, tolerance_pct: float = 0.01) -> list:
        """
        Gabungkan level yang jaraknya kurang dari tolerance_pct (default 1%).
        
        Ini membuat S/R lebih akurat karena menggabungkan level yang "hampir sama"
        dan menghitung total touches-nya.
        """
        clustered = []
        
        for level_type, price in levels:
            merged = False
            for cluster in clustered:
                if cluster["type"] == level_type:
                    distance = abs(cluster["price"] - price) / price
                    if distance < tolerance_pct:
                        # Merge: rata-rata harga dan tambah touches
                        cluster["price"] = (cluster["price"] + price) / 2
                        cluster["touches"] += 1
                        merged = True
                        break
            
            if not merged:
                clustered.append({
                    "type": level_type,
                    "price": price,
                    "touches": 1
                })
        
        return clustered

    def _calculate_derived_metrics(self, result: Dict, current_price: float) -> Dict:
        """Calculate risk/reward ratio and distances to S/R levels."""
        support_1 = result.get('support_1', 0)
        resistance_1 = result.get('resistance_1', 0)
        
        if support_1 > 0 and resistance_1 > 0:
            # Distance percentages
            result['distance_to_support_pct'] = ((current_price - support_1) / current_price) * 100
            result['distance_to_resistance_pct'] = ((resistance_1 - current_price) / current_price) * 100
            
            # Risk/Reward ratio
            risk = current_price - support_1
            reward = resistance_1 - current_price
            result['risk_reward_ratio'] = reward / risk if risk > 0 else 0
        else:
            result['distance_to_support_pct'] = 0
            result['distance_to_resistance_pct'] = 0
            result['risk_reward_ratio'] = 0
        
        return result

    def _classify_price_zone(
        self, 
        price: float, 
        support_1: float, 
        resistance_1: float
    ) -> str:
        """
        Classify current price zone relative to S/R levels.
        
        Zones:
        - BELOW_SUPPORT: Price below S1 (very bearish)
        - IN_SUPPORT: Price near S1 (potential buy zone)
        - MIDDLE: Between S1 and R1 (neutral)
        - IN_RESISTANCE: Price near R1 (potential sell zone)
        - ABOVE_RESISTANCE: Price above R1 (bullish breakout)
        """
        if support_1 == 0 or resistance_1 == 0:
            return "UNKNOWN"
        
        tolerance = 0.02  # 2% tolerance for zone boundaries
        
        if price <= support_1 * (1 - tolerance):
            return "BELOW_SUPPORT"
        elif support_1 * (1 - tolerance) < price <= support_1 * (1 + tolerance):
            return "IN_SUPPORT"
        elif resistance_1 * (1 - tolerance) < price <= resistance_1 * (1 + tolerance):
            return "IN_RESISTANCE"
        elif price > resistance_1 * (1 + tolerance):
            return "ABOVE_RESISTANCE"
        else:
            return "MIDDLE"

    def _empty_result(self) -> Dict:
        """Return empty result when detection fails."""
        return {
            'support_1': 0, 'support_2': 0,
            'resistance_1': 0, 'resistance_2': 0,
            'price_zone': 'UNKNOWN',
            'risk_reward_ratio': 0,
            'distance_to_support_pct': 0,
            'distance_to_resistance_pct': 0,
            'detection_method': 'none',
            'error': 'Not enough data for S/R detection'
        }
