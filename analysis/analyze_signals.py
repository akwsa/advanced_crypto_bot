"""
Analyze a single trading pair to determine BUY/SELL recommendation.
Analyzes technical indicators and generates actionable trading signals.
"""
import asyncio
import pandas as pd
from typing import Dict, Optional, Any
from datetime import datetime

from core.database import Database
from core.logger import CustomLogger
from core.utils import Utils
from api.indodax_api import IndodaxAPI
from analysis.technical_analysis import TechnicalAnalysis
from analysis.signal_analyzer import SignalAnalyzer

logger = CustomLogger('analyze_signals').get_logger()


class AnalyzeSignals:
    """Analyze a single trading pair for BUY/SELL recommendation"""
    
    def __init__(self):
        self.db = Database()
        self.indodax = IndodaxAPI()
        self.utils = Utils()
    
    async def analyze(self, pair: str) -> Dict[str, Any]:
        """
        Analyze a single trading pair for MAXIMUM PROFIT.
        
        Args:
            pair: Trading pair (e.g., 'BTC/IDR')
            
        Returns:
            Dict containing:
            - recommendation: 'BUY', 'SELL', 'STRONG_BUY', 'STRONG_SELL', or 'HOLD'
            - confidence: float 0-1
            - reasons: list of analysis details
            - indicators: dict of indicator values
            - price: current price
            - entry_price: recommended entry price
            - stop_loss: recommended stop loss
            - take_profit: recommended take profit
            - risk_reward: risk-reward ratio
        """
        try:
            pair = pair.strip().upper()
            
            current_price = self._get_price(pair)
            if not current_price:
                return {
                    'recommendation': 'ERROR',
                    'confidence': 0,
                    'reasons': [f'No price data for {pair}'],
                    'indicators': {},
                    'price': None
                }
            
            df = self._get_historical_data(pair)
            if df is None or df.empty or len(df) < 30:
                return {
                    'recommendation': 'HOLD',
                    'confidence': 0.3,
                    'reasons': ['Insufficient data for analysis'],
                    'indicators': {},
                    'price': current_price
                }
            
            ta = TechnicalAnalysis(df)
            signals = ta.get_signals()
            
            recommendation = signals.get('recommendation', 'HOLD')
            strength = signals.get('strength', 0)
            indicator_scores = signals.get('indicator_scores', [])
            indicators = signals.get('indicators', {})
            
            rsi_val = df['rsi'].iloc[-1] if 'rsi' in df.columns else 50
            macd_val = df['macd'].iloc[-1] if 'macd' in df.columns else 0
            macd_sig = df['macd_signal'].iloc[-1] if 'macd_signal' in df.columns else 0
            volume_ratio = df['volume'].iloc[-1] / df['volume_sma'].iloc[-1] if 'volume_sma' in df.columns and df['volume_sma'].iloc[-1] > 0 else 1.0
            close = df['close'].iloc[-1]
            
            reasons = []
            buy_score = 0
            sell_score = 0
            
            # RSI Analysis - KEY for entry timing
            if rsi_val < 30:
                reasons.append(f"🟢 RSI oversold ({rsi_val:.1f}) - POTENTIAL BOTTOM")
                buy_score += 3
            elif rsi_val < 40:
                reasons.append(f"🟢 RSI lower half ({rsi_val:.1f}) - good entry")
                buy_score += 1
            elif rsi_val > 70:
                reasons.append(f"🔴 RSI overbought ({rsi_val:.1f}) - RISK HIGH")
                sell_score += 3
            elif rsi_val > 60:
                reasons.append(f"🔴 RSI upper half ({rsi_val:.1f})")
                sell_score += 1
            
            # MACD Analysis - KEY for momentum
            if macd_val > macd_sig:
                reasons.append("🟢 MACD bullish - momentum UP")
                buy_score += 2
            else:
                reasons.append("🔴 MACD bearish - momentum DOWN")
                sell_score += 2
            
            # MA Trend Analysis
            sma_9 = df['sma_9'].iloc[-1] if 'sma_9' in df.columns else close
            sma_20 = df['sma_20'].iloc[-1] if 'sma_20' in df.columns else close
            if close > sma_20 > sma_9:
                reasons.append("🟢 MA alignment UP - strong trend")
                buy_score += 2
            elif close < sma_20 < sma_9:
                reasons.append("🔴 MA alignment DOWN - downtrend")
                sell_score += 2
            
            # Volume Analysis
            if volume_ratio > 1.5:
                reasons.append(f"🟢 High volume ({volume_ratio:.1f}x) - strong conviction")
                buy_score += 1
                sell_score += 1
            elif volume_ratio > 1.2:
                reasons.append(f"📊 Elevated volume ({volume_ratio:.1f}x)")
            
            # Bollinger Bands
            if 'bb_lower' in df.columns and close < df['bb_lower'].iloc[-1]:
                reasons.append("🟢 Price at lower BB - oversold bounce")
                buy_score += 2
            elif 'bb_upper' in df.columns and close > df['bb_upper'].iloc[-1]:
                reasons.append("🔴 Price at upper BB - overbought")
                sell_score += 2
            
            # Determine final recommendation based on score
            if buy_score > sell_score + 2:
                final_rec = 'STRONG_BUY'
            elif buy_score > sell_score:
                final_rec = 'BUY'
            elif sell_score > buy_score + 2:
                final_rec = 'STRONG_SELL'
            elif sell_score > buy_score:
                final_rec = 'SELL'
            else:
                final_rec = 'HOLD'
            
            # Calculate confidence
            max_score = max(buy_score, sell_score, 1)
            confidence = min(abs(buy_score - sell_score) / max_score, 1.0)
            
            # Calculate SL/TP levels
            from core.config import Config
            stop_loss_pct = Config.STOP_LOSS_PCT / 100
            take_profit_pct = Config.TAKE_PROFIT_PCT / 100
            
            if final_rec in ['BUY', 'STRONG_BUY']:
                entry_price = current_price
                stop_loss = current_price * (1 - stop_loss_pct)
                take_profit = current_price * (1 + take_profit_pct)
                risk = current_price - stop_loss
                reward = take_profit - current_price
                risk_reward = reward / risk if risk > 0 else 0
            elif final_rec in ['SELL', 'STRONG_SELL']:
                entry_price = current_price
                stop_loss = current_price * (1 + stop_loss_pct)
                take_profit = current_price * (1 - take_profit_pct)
                risk = stop_loss - current_price
                reward = current_price - take_profit
                risk_reward = reward / risk if risk > 0 else 0
            else:
                entry_price = current_price
                stop_loss = current_price * 0.98
                take_profit = current_price * 1.05
                risk_reward = 2.0
            
            return {
                'recommendation': final_rec,
                'confidence': confidence,
                'reasons': reasons,
                'indicators': {
                    'rsi': rsi_val,
                    'macd': macd_val,
                    'macd_signal': macd_sig,
                    'volume_ratio': volume_ratio,
                    'buy_score': buy_score,
                    'sell_score': sell_score,
                    'strength': strength
                },
                'price': current_price,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk_reward': risk_reward,
                'pair': pair,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing {pair}: {e}")
            return {
                'recommendation': 'ERROR',
                'confidence': 0,
                'reasons': [str(e)],
                'indicators': {},
                'price': None
            }
    
    def _get_price(self, pair: str) -> Optional[float]:
        """Get current price for pair"""
        try:
            ticker = self.indodax.get_ticker(pair)
            if ticker:
                return ticker.get('last')
        except Exception as e:
            logger.warning(f"Error getting price for {pair}: {e}")
        return None
    
    def _get_historical_data(self, pair: str, limit: int = 100) -> Optional[pd.DataFrame]:
        """Get historical price data from database"""
        try:
            df = self.db.get_price_history(pair, limit=limit)
            return df if df is not None and not df.empty else None
        except Exception as e:
            logger.warning(f"Error getting historical data for {pair}: {e}")
        return None
    
    def format_message(self, result: Dict[str, Any]) -> str:
        """Format analysis result as Telegram message with SL/TP for trading"""
        pair = result.get('pair', 'N/A')
        price = result.get('price')
        recommendation = result.get('recommendation', 'HOLD')
        confidence = result.get('confidence', 0)
        reasons = result.get('reasons', [])
        indicators = result.get('indicators', {})
        
        entry_price = result.get('entry_price', price)
        stop_loss = result.get('stop_loss')
        take_profit = result.get('take_profit')
        risk_reward = result.get('risk_reward', 0)
        
        price_str = f"Rp {price:,.0f}" if price else "N/A"
        
        rec_emoji = {
            'STRONG_BUY': '🟢🟢',
            'BUY': '🟢',
            'HOLD': '⏸️',
            'SELL': '🔴',
            'STRONG_SELL': '🔴🔴',
            'ERROR': '❌'
        }.get(recommendation, '❓')
        
        text = f"""
📊 <b>ANALISIS: {pair}</b>

💰 <b>Harga Saat Ini:</b> <code>{price_str}</code>

🎯 <b>Rekomendasi:</b> {rec_emoji} <code>{recommendation}</code>
📈 <b>Confidence:</b> <code>{confidence:.0%}</code>

📋 <b>Indicator Scores:</b>
"""
        if indicators:
            text += f"• RSI: <code>{indicators.get('rsi', 50):.1f}</code>\n"
            text += f"• MACD: <code>{indicators.get('macd', 0):.2f}</code>\n"
            text += f"• Volume: <code>{indicators.get('volume_ratio', 1):.1f}x</code>\n"
            text += f"• Buy Score: <code>{indicators.get('buy_score', 0)}</code>\n"
            text += f"• Sell Score: <code>{indicators.get('sell_score', 0)}</code>\n"
        
        if recommendation in ['BUY', 'STRONG_BUY', 'SELL', 'STRONG_SELL']:
            sl_str = f"Rp {stop_loss:,.0f}" if stop_loss else "N/A"
            tp_str = f"Rp {take_profit:,.0f}" if take_profit else "N/A"
            text += f"""
🎯 <b>Entry Plan:</b>
• Entry: <code>Rp {entry_price:,.0f}</code> (market)
• Stop Loss: <code>{sl_str}</code>
• Take Profit: <code>{tp_str}</code>
• Risk/Reward: <code>{risk_reward:.1f}:1</code>
"""
        
        text += "\n🧠 <b>Analisis Detail:</b>\n"
        for reason in reasons:
            text += f"• {reason}\n"
        
        return text


async def analyze_pair(pair: str) -> Dict[str, Any]:
    """
    Quick function to analyze a single trading pair.
    
    Args:
        pair: Trading pair (e.g., 'BTC/IDR')
        
    Returns:
        Analysis result dict
    """
    analyzer = AnalyzeSignals()
    return await analyzer.analyze(pair)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python analyze_signals.py <PAIR>")
        print("Example: python analyze_signals.py BTC/IDR")
        sys.exit(1)
    
    pair = sys.argv[1]
    result = asyncio.run(analyze_pair(pair))
    
    analyzer = AnalyzeSignals()
    message = analyzer.format_message(result)
    print(message)