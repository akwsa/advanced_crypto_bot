import hashlib
import hmac
import time
import requests
import json
from core.config import Config
import logging
import asyncio
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class IndodaxAPI:
    def __init__(self, api_key=None, secret_key=None):
        self.api_key = api_key or Config.INDODAX_API_KEY
        self.secret_key = secret_key or Config.INDODAX_SECRET_KEY
        self.base_url = Config.INDODAX_REST_URL
        self.session = requests.Session()

    def _generate_signature(self, post_params):
        """Generate HMAC signature for API requests"""
        # Signature is HMAC-SHA512 of the POST body (totalParams)
        # Parameters must be sorted alphabetically
        post_data = '&'.join([f"{k}={v}" for k, v in sorted(post_params.items())])
        signature = hmac.new(
            self.secret_key.encode(),
            post_data.encode(),
            hashlib.sha512
        ).hexdigest()
        return signature

    def _generate_signature_with_data(self, post_params):
        """Generate HMAC signature with pre-formatted post data"""
        post_data = '&'.join([f"{k}={v}" for k, v in sorted(post_params.items())])
        signature = hmac.new(
            self.secret_key.encode(),
            post_data.encode(),
            hashlib.sha512
        ).hexdigest()
        return signature

    def _get_headers(self, post_params):
        """Generate headers for authenticated requests"""
        signature = self._generate_signature(post_params)
        timestamp = post_params.get('timestamp', str(int(time.time() * 1000)))
        return {
            'Key': self.api_key,
            'Sign': signature,
            'Timestamp': timestamp,
            'Content-Type': 'application/x-www-form-urlencoded'
        }

    def get_ticker(self, pair, retries=3):
        """Get current ticker for a trading pair with retry logic"""
        pair_symbol = pair.replace('/', '').lower()
        url = f"{self.base_url}/api/ticker/{pair_symbol}"

        for attempt in range(retries):
            try:
                # Increased timeout for unreliable networks: 10s connect, 20s read
                response = self.session.get(
                    url,
                    timeout=(10, 20),  # (connect_timeout, read_timeout)
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'ticker' in data:
                        t = data['ticker']
                        return {
                            'pair': pair,
                            'last': float(t.get('last', 0)),
                            'high': float(t.get('high', 0)),
                            'low': float(t.get('low', 0)),
                            'volume': float(t.get('vol', t.get('volume', 0))),
                            'bid': float(t.get('buy', 0)),
                            'ask': float(t.get('sell', 0)),
                            'timestamp': time.time()
                        }
                
                elif response.status_code == 429:
                    # Rate limit - wait and retry
                    wait_time = 2 * (attempt + 1)  # 2s, 4s, 6s
                    logger.warning(f"⚠️ Rate limit (429) for {pair}, retry in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                    
                else:
                    logger.debug(f"Ticker API returned {response.status_code} for {pair}")
                    if attempt < retries - 1:
                        time.sleep(1)
                        continue
                    
            except requests.exceptions.Timeout:
                if attempt < retries - 1:
                    wait_time = 2 * (attempt + 1)
                    logger.warning(f"⏱️ Timeout for {pair} (attempt {attempt+1}/{retries}), retry in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"❌ Timeout getting ticker for {pair} after {retries} attempts")
                    return None
                    
            except requests.exceptions.ConnectionError as e:
                if attempt < retries - 1:
                    wait_time = 2 * (attempt + 1)
                    logger.warning(f"🔌 Connection error for {pair}, retry in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"❌ Connection error getting ticker for {pair}: {e}")
                    return None
                    
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "Too Many Requests" in error_str:
                    if attempt < retries - 1:
                        time.sleep(2 * (attempt + 1))
                        continue
                else:
                    logger.debug(f"Error getting ticker for {pair}: {e}")
                    if attempt < retries - 1:
                        time.sleep(1)
                        continue
                    return None
        
        logger.error(f"❌ Failed to get ticker for {pair} after {retries} attempts")
        return None

    def get_all_tickers(self):
        """Get ALL tickers from Indodax (public endpoint)"""
        try:
            # Indodax has a public endpoint to get all summaries
            url = f"{self.base_url}/api/summaries"
            logger.debug(f"Fetching all tickers from: {url}")

            response = self.session.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})

            if response.status_code == 200:
                data = response.json()
                if 'tickers' in data:
                    tickers = data['tickers']
                    
                    # Get 24h price changes if available
                    prices_24h = data.get('prices_24h', {})
                    
                    result = []

                    for pair, t in tickers.items():
                        try:
                            last = float(t.get('last', 0))
                            high = float(t.get('high', 0))
                            low = float(t.get('low', 0))
                            buy = float(t.get('buy', 0))
                            sell = float(t.get('sell', 0))
                            vol_idr = float(t.get('vol_idr', 0))
                            vol_coin = float(t.get('vol_btc', t.get('vol', 0)))
                            
                            # Calculate 24h change percentage
                            change_percent = None
                            
                            # FIX: prices_24h uses NO underscore (btcidr), but tickers uses underscore (btc_idr)
                            pair_no_underscore = pair.replace('_', '')
                            price_24h_ago = prices_24h.get(pair_no_underscore)
                            
                            if price_24h_ago is not None:
                                try:
                                    price_24h = float(price_24h_ago)
                                    if price_24h > 0:
                                        change_percent = round(((last - price_24h) / price_24h) * 100, 2)
                                except (ValueError, TypeError):
                                    pass

                            result.append({
                                'pair': pair.upper(),
                                'last': last,
                                'high': high,
                                'low': low,
                                'volume': vol_idr,  # Volume in IDR (Rupiah) - for sorting
                                'volume_coin': vol_coin,  # Volume in coin
                                'bid': buy,
                                'ask': sell,
                                'change_percent': change_percent,
                                'timestamp': time.time()
                            })
                        except (ValueError, TypeError) as e:
                            logger.debug(f"Failed to parse ticker {pair}: {e}")
                            continue

                    logger.info(f"✅ Fetched {len(result)} tickers from Indodax")
                    return result
                else:
                    logger.warning(f"⚠️ No 'tickers' key in response: {list(data.keys())[:5]}")
            else:
                logger.warning(f"⚠️ Summaries API returned {response.status_code}")

            return []
        except Exception as e:
            logger.error(f"❌ Error fetching all tickers: {e}")
            return []

    def _get_change_percent(self, pair, last, low, high):
        """Try to get accurate change_percent from individual ticker"""
        try:
            # First try: individual ticker endpoint (has change_percent)
            url = f"{self.base_url}/api/ticker/{pair}"
            response = self.session.get(url, timeout=3, headers={'User-Agent': 'Mozilla/5.0'})
            
            if response.status_code == 200:
                data = response.json()
                if 'ticker' in data:
                    ticker = data['ticker']
                    # Indodax provides 'change_percent' in individual ticker
                    cp = ticker.get('change_percent')
                    if cp is not None:
                        return round(float(cp), 2)
            
            # Fallback: calculate from low if available
            if low > 0 and high != low:
                return round(((last - low) / low) * 100, 2)
            
            return None
        except Exception as e:
            logger.debug(f"Error calculating ticker data: {e}")
            # If individual ticker fails, calculate from available data
            if low > 0 and high != low:
                return round(((last - low) / low) * 100, 2)
            return None

    def get_orderbook(self, pair, limit=10):
        """Get order book for a trading pair"""
        try:
            # Indodax uses different endpoint format
            pair_symbol = pair.replace('/', '').lower()
            
            # Try multiple endpoint formats based on Indodax API docs
            endpoints = [
                f"{self.base_url}/api/depth/{pair_symbol}",      # API v2 format
                f"{self.base_url}/depth/{pair_symbol}",           # Legacy format
                f"{self.base_url}/api/{pair_symbol}/depth",       # Alternative format
            ]
            
            for i, url in enumerate(endpoints):
                logger.debug(f"Order book attempt {i+1}: {url}")
                response = self.session.get(url, timeout=5)
                logger.debug(f"Order book response {i+1}: {response.status_code}")
                
                if response.status_code == 200 and response.text:
                    try:
                        data = response.json()
                        logger.debug(f"Order book success: {len(data.get('buy', []))} bids, {len(data.get('sell', []))} asks")
                        return {
                            'pair': pair,
                            'bids': data.get('buy', [])[:limit],
                            'asks': data.get('sell', [])[:limit],
                            'timestamp': time.time()
                        }
                    except json.JSONDecodeError as e:
                        logger.debug(f"Order book JSON decode failed: {e}")
                        continue  # Try next endpoint
            
            logger.warning(f"Order book API failed for {pair} after trying all endpoints")
            return None
            
        except requests.exceptions.Timeout:
            logger.error(f"Order book API timeout for {pair}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Order book API request failed for {pair}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting orderbook: {e}")
        return None

    def get_balance(self):
        """Get account balance"""
        try:
            url = f"{self.base_url}/tapi"
            
            # Use nonce instead of timestamp for better compatibility
            nonce = int(time.time() * 1000000)  # Microsecond-based nonce

            post_params = {
                'method': 'getInfo',
                'nonce': str(nonce)
            }

            post_data = '&'.join([f"{k}={v}" for k, v in sorted(post_params.items())])
            signature = self._generate_signature_with_data(post_params)

            headers = {
                'Key': self.api_key,
                'Sign': signature,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            logger.debug(f"Balance request: {post_data}")
            response = self.session.post(url, headers=headers, data=post_data, timeout=10)
            
            logger.debug(f"Balance response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Balance API HTTP {response.status_code}: {response.text[:200]}")
                return None

            data = response.json()

            # Check for API errors
            if 'error' in data:
                logger.error(f"Balance API error: {data['error']}")
                return None

            if data.get('success') == 1 and 'return' in data:
                return data['return']
            
            logger.error(f"Balance API unexpected response: {data}")
            return None
            
        except requests.exceptions.Timeout:
            logger.error("Balance API timeout")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Balance API request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return None

    def get_open_orders(self, pair=None):
        """Get open orders"""
        try:
            url = f"{self.base_url}/tapi"
            nonce = int(time.time() * 1000000)

            if pair:
                pair_symbol = pair.replace('/', '_').lower()
                post_params = {
                    'method': 'openOrders',
                    'pair': pair_symbol,
                    'nonce': str(nonce)
                }
            else:
                post_params = {
                    'method': 'openOrders',
                    'nonce': str(nonce)
                }

            post_data = '&'.join([f"{k}={v}" for k, v in sorted(post_params.items())])
            signature = self._generate_signature_with_data(post_params)
            headers = {
                'Key': self.api_key,
                'Sign': signature,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = self.session.post(url, headers=headers, data=post_data, timeout=10)
            data = response.json()

            return data.get('return', {}).get('orders', [])
        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
        return []

    def create_order(self, pair, trade_type, price, amount, max_slippage=None):
        """Create a buy/sell order with optional slippage protection.
        
        Args:
            pair: Trading pair (e.g., 'btcidr')
            trade_type: 'buy' or 'sell'
            price: Order price
            amount: Order amount in coin units
            max_slippage: Max slippage % (default from Config.SLIPPAGE_MAX_PCT)
            
        Returns:
            dict: Order result or None if slippage exceeded or error
        """
        from core.config import Config
        
        if max_slippage is None:
            max_slippage = Config.SLIPPAGE_MAX_PCT
        
        try:
            pair_symbol = pair.replace('/', '_').lower()
            
            # Get current market price for slippage check
            ticker = self.get_ticker(pair)
            if ticker:
                market_price = ticker.get('last', price)
            
                if trade_type.lower() == 'buy':
                    # Slippage = actual fill vs expected
                    slippage = (market_price - price) / price if price > 0 else 0
                else:  # sell
                    slippage = (price - market_price) / market_price if market_price > 0 else 0
                
                if abs(slippage) > max_slippage:
                    logger.warning(f"🚫 Slippage protection: {slippage*100:.2f}% > {max_slippage*100:.2f}%")
                    if Config.SLIPPAGE_CANCEL_ENABLED:
                        logger.info("🚫 Order cancelled due to excessive slippage")
                        return {'success': 0, 'error': 'SLIPPAGE_EXCEEDED'}
            
            url = f"{self.base_url}/tapi"
            nonce = int(time.time() * 1000000)

            # Get coin name from pair (e.g., 'pippin' from 'pippin_idr')
            coin_name = pair_symbol.split('_')[0]

            # Determine order parameters based on type
            post_params = {
                'method': 'trade',
                'pair': pair_symbol,
                'type': trade_type.lower(),
                'price': str(price),
                'nonce': str(nonce),
                'order_type': 'limit'
            }

            # Add amount parameter based on order type
            if trade_type.lower() == 'buy':
                # FIX: Indodax requires BOTH 'idr' AND coin quantity for buy orders
                # Round to max 8 decimal places for Indodax API
                total_idr = int(price * amount)
                coin_amount_rounded = round(amount, 8)
                post_params['idr'] = str(total_idr)
                post_params[coin_name] = f"{coin_amount_rounded:.8f}".rstrip('0').rstrip('.')  # Remove trailing zeros
            else:
                coin_amount_rounded = round(amount, 8)
                post_params[coin_name] = f"{coin_amount_rounded:.8f}".rstrip('0').rstrip('.')

            post_data = '&'.join([f"{k}={v}" for k, v in sorted(post_params.items())])
            signature = self._generate_signature_with_data(post_params)
            headers = {
                'Key': self.api_key,
                'Sign': signature,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            logger.info(f"POST {url}")
            logger.info(f"Params: {post_params}")
            logger.info(f"POST data: {post_data}")

            response = self.session.post(url, headers=headers, data=post_data, timeout=10)
            data = response.json()

            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response: {data}")
            return data
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            logger.error(f"Response status: {response.status_code if 'response' in dir() else 'N/A'}")
            logger.error(f"Response text: {response.text if 'response' in dir() else 'N/A'}")
        return None

    def cancel_order(self, pair, order_id):
        """Cancel an order"""
        try:
            pair_symbol = pair.replace('/', '_').lower()
            url = f"{self.base_url}/tapi"
            nonce = int(time.time() * 1000000)

            post_params = {
                'method': 'cancelOrder',
                'pair': pair_symbol,
                'order_id': str(order_id),
                'nonce': str(nonce)
            }

            post_data = '&'.join([f"{k}={v}" for k, v in sorted(post_params.items())])
            signature = self._generate_signature_with_data(post_params)
            headers = {
                'Key': self.api_key,
                'Sign': signature,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = self.session.post(url, headers=headers, data=post_data, timeout=10)
            data = response.json()

            logger.info(f"Order cancelled: {data}")
            return data
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
        return None

    def get_trade_history(self, pair=None, limit=100):
        """Get trade history"""
        try:
            url = f"{self.base_url}/tapi"
            nonce = int(time.time() * 1000000)

            if pair:
                pair_symbol = pair.replace('/', '_').lower()
                post_params = {
                    'method': 'orderHistory',
                    'pair': pair_symbol,
                    'nonce': str(nonce)
                }
            else:
                post_params = {
                    'method': 'orderHistory',
                    'nonce': str(nonce)
                }

            post_data = '&'.join([f"{k}={v}" for k, v in sorted(post_params.items())])
            signature = self._generate_signature_with_data(post_params)
            headers = {
                'Key': self.api_key,
                'Sign': signature,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = self.session.post(url, headers=headers, data=post_data, timeout=10)
            data = response.json()

            return data.get('return', {}).get('orders', [])
        except Exception as e:
            logger.error(f"Error getting trade history: {e}")
        return []

    def test_connection(self):
        """Test API connection"""
        try:
            # Test public endpoint first
            response = self.session.get(f"{self.base_url}/ticker/btcidr")
            if response.status_code == 200:
                logger.info("✅ Indodax public API connected")
                
                # Test authenticated endpoint
                balance = self.get_balance()
                if balance:
                    logger.info("✅ Indodax API authenticated")
                    return True
                else:
                    logger.warning("⚠️ Indodax API authentication failed - check API keys")
                    return False
            else:
                logger.error(f"❌ Indodax API connection failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ Indodax API test error: {e}")
            return False

    # =====================================================================
    # ASYNC WRAPPER METHODS
    # =====================================================================
    # These provide async interface for compatibility with async codebase

    async def get_ticker_async(self, pair: str, retries: int = 3) -> Optional[Dict]:
        """Async version of get_ticker using thread pool executor.

        This allows the ticker fetch to run in a thread pool without
        blocking the event loop.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,  # Default executor
            lambda: self.get_ticker(pair, retries)
        )

    async def get_all_tickers_async(self) -> List[Dict]:
        """Async version of get_all_tickers."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_all_tickers)

    async def get_orderbook_async(self, pair: str, limit: int = 10) -> Optional[Dict]:
        """Async version of get_orderbook."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.get_orderbook(pair, limit)
        )

    async def get_balance_async(self) -> Optional[Dict]:
        """Async version of get_balance."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_balance)

    async def get_trade_history_async(self, pair: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Async version of get_trade_history."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.get_trade_history(pair, limit)
        )

    async def test_connection_async(self) -> bool:
        """Async version of test_connection."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.test_connection)

    async def batch_get_tickers(self, pairs: List[str], max_concurrent: int = 5) -> Dict[str, Optional[Dict]]:
        """Fetch multiple tickers concurrently with rate limiting.

        Args:
            pairs: List of trading pairs to fetch
            max_concurrent: Maximum concurrent requests

        Returns:
            Dict mapping pair to ticker data (or None if failed)
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_limit(pair: str) -> tuple:
            async with semaphore:
                # Add small delay between requests to respect rate limits
                await asyncio.sleep(0.1)
                result = await self.get_ticker_async(pair)
                return pair, result

        tasks = [fetch_with_limit(pair) for pair in pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dict, handling any exceptions
        tickers = {}
        for pair, result in results:
            if isinstance(result, Exception):
                logger.warning(f"Failed to fetch {pair}: {result}")
                tickers[pair] = None
            else:
                tickers[pair] = result

        return tickers


# Create global instance
indodax = IndodaxAPI()
