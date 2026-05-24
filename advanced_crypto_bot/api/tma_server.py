# Tujuan: FastAPI backend untuk Telegram Mini App dashboard.
# Caller: TMA frontend (HTML/JS di Telegram WebView).
# Dependensi: fastapi, uvicorn (optional), core.database, analysis.adaptive_learning.
# Main Functions: TMA API endpoints.
# Side Effects: DB reads only (no writes).

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# We use a simple Flask-like approach to avoid adding new dependencies
# Since the bot already uses python-telegram-bot, we'll create a simple HTTP handler

from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import logging

logger = logging.getLogger('crypto_bot')


class TMADataProvider:
    """Provides data for TMA dashboard."""
    
    def __init__(self, db):
        self.db = db
    
    def get_portfolio_summary(self, user_id: int = 1) -> Dict:
        """Get portfolio summary for dashboard."""
        try:
            open_trades = self.db.get_open_trades(user_id)
            balance = self.db.get_balance(user_id)
            
            total_exposure = sum(t['total'] for t in open_trades)
            total_pnl = sum(
                (t.get('profit_loss', 0) or 0) for t in open_trades
            )
            
            positions = []
            for trade in open_trades[:20]:  # Limit to 20
                entry = trade['price']
                # Assume current price = entry for simplicity (bot will provide real price)
                current_price = entry  
                pnl_pct = ((current_price - entry) / entry * 100) if entry > 0 else 0
                positions.append({
                    'pair': trade['pair'],
                    'entry_price': entry,
                    'amount': trade['amount'],
                    'total': trade['total'],
                    'pnl_pct': round(pnl_pct, 2),
                })
            
            return {
                'balance': balance,
                'open_positions_count': len(open_trades),
                'total_exposure': total_exposure,
                'unrealized_pnl': total_pnl,
                'positions': positions,
            }
        except Exception as e:
            logger.error(f"TMA portfolio error: {e}")
            return {'error': str(e)}
    
    def get_signal_heatmap(self, limit: int = 50) -> List[Dict]:
        """Get recent signals for heatmap."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                columns = {
                    row["name"]
                    for row in cursor.execute("PRAGMA table_info(signals)").fetchall()
                }
                if not columns:
                    return []

                pair_col = "pair" if "pair" in columns else "symbol" if "symbol" in columns else None
                time_col = "received_at" if "received_at" in columns else "timestamp" if "timestamp" in columns else "created_at"
                if not pair_col or "recommendation" not in columns:
                    logger.warning(f"TMA heatmap unavailable: unsupported signals schema columns={sorted(columns)}")
                    return []

                confidence_expr = (
                    "ml_confidence"
                    if "ml_confidence" in columns
                    else "confidence"
                    if "confidence" in columns
                    else "0.0"
                )
                strength_expr = "combined_strength" if "combined_strength" in columns else "0.0"
                price_expr = "price" if "price" in columns else "0.0"

                query = f'''
                    SELECT {pair_col} AS pair,
                           recommendation,
                           {confidence_expr} AS ml_confidence,
                           {strength_expr} AS combined_strength,
                           {price_expr} AS price,
                           {time_col} AS received_at
                    FROM signals
                    ORDER BY {time_col} DESC
                    LIMIT ?
                '''
                cursor.execute(query, (limit,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"TMA heatmap error: {e}")
            return []
    
    def get_adaptive_status(self) -> List[Dict]:
        """Get adaptive thresholds status."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT pair, win_rate_7d, profit_factor_7d, total_trades_7d,
                           confidence_threshold_buy, position_size_multiplier, skip_pair
                    FROM adaptive_thresholds
                    ORDER BY profit_factor_7d DESC
                ''')
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"TMA adaptive error: {e}")
            return []
    
    def get_trade_stats(self, days: int = 7) -> Dict:
        """Get trade statistics."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cutoff = datetime.now() - timedelta(days=days)
                
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN profit_loss_pct > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN profit_loss_pct <= 0 THEN 1 ELSE 0 END) as losses,
                        AVG(profit_loss_pct) as avg_pnl,
                        SUM(profit_loss_pct) as total_pnl
                    FROM trades
                    WHERE status = 'CLOSED' AND closed_at >= ?
                ''', (cutoff,))
                row = cursor.fetchone()
                
                return {
                    'period_days': days,
                    'total_trades': row['total'] or 0,
                    'wins': row['wins'] or 0,
                    'losses': row['losses'] or 0,
                    'win_rate': (row['wins'] or 0) / (row['total'] or 1),
                    'avg_pnl_pct': row['avg_pnl'] or 0,
                    'total_pnl_pct': row['total_pnl'] or 0,
                }
        except Exception as e:
            logger.error(f"TMA stats error: {e}")
            return {}


class TMARequestHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for TMA API."""
    
    data_provider = None
    
    def do_GET(self):
        """Handle GET requests."""
        path = self.path
        
        # Serve static HTML for root path
        if path == '/' or path == '/index.html':
            self._serve_static_html()
            return
        
        # API endpoints
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        if path == '/api/portfolio':
            data = self.data_provider.get_portfolio_summary()
        elif path == '/api/heatmap':
            data = self.data_provider.get_signal_heatmap()
        elif path == '/api/adaptive':
            data = self.data_provider.get_adaptive_status()
        elif path == '/api/stats':
            data = self.data_provider.get_trade_stats()
        elif path == '/api/health':
            data = {'status': 'ok', 'time': datetime.now().isoformat()}
        else:
            data = {'error': 'Not found'}
        
        self.wfile.write(json.dumps(data, default=str).encode())
    
    def _serve_static_html(self):
        """Serve the TMA dashboard HTML."""
        try:
            webapp_dir = os.path.join(os.path.dirname(__file__), '..', 'webapp')
            html_path = os.path.join(webapp_dir, 'index.html')
            
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(html_content.encode())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Error loading dashboard: {e}".encode())
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def start_tma_server(db, port: int = 8080):
    """Start TMA API server in background thread."""
    TMARequestHandler.data_provider = TMADataProvider(db)
    
    server = HTTPServer(('0.0.0.0', port), TMARequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    
    logger.info(f"📱 TMA API server started on http://0.0.0.0:{port}")
    return server
