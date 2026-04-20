import websocket
import json
import hmac
import hashlib
import time
import logging
from datetime import datetime
from core.config import Config

logger = logging.getLogger(__name__)


class WebSocketHandler:
    def __init__(self, on_message_callback, on_connect_callback=None):
        self.ws_url = Config.INDODAX_WS_URL
        self.ws = None
        self.on_message_callback = on_message_callback
        self.on_connect_callback = on_connect_callback
        self.is_connected = False
        self.subscribed_channels = set()
        self.api_key = Config.INDODAX_API_KEY
        self.secret_key = Config.INDODAX_SECRET_KEY
        self.use_auth = bool(self.api_key and self.secret_key)
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5  # seconds
        
    def connect(self):
        """Connect to WebSocket with auto-reconnect"""
        logger.info(f"🔌 Connecting to {self.ws_url}...")
        logger.info(f"🔐 Authentication: {'Enabled' if self.use_auth else 'Disabled (Public Only)'}")

        try:
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )

            # Run in separate thread
            import threading
            ws_thread = threading.Thread(target=self._run_ws, daemon=True)
            ws_thread.start()

        except Exception as e:
            logger.error(f"❌ Failed to connect: {e}")
            self._schedule_reconnect()
    
    def _run_ws(self):
        """Run WebSocket with automatic ping"""
        logger.info("🚀 Starting WebSocket main loop...")
        logger.info(f"📋 Using ping_interval=30, ping_timeout=10")
        
        try:
            # run_forever will handle ping/pong automatically
            # ping_interval: send ping every 30 seconds
            # ping_timeout: wait 10 seconds for pong response
            self.ws.run_forever(
                ping_interval=30,
                ping_timeout=10,
                reconnect=5,  # Auto reconnect delay
                http_proxy_host=None,
                http_proxy_port=None,
                ping_payload=""  # Empty ping payload
            )
        except Exception as e:
            logger.error(f"❌ WebSocket main loop error: {e}")
            self._schedule_reconnect()
    
    def _schedule_reconnect(self):
        """Schedule reconnect attempt with exponential backoff"""
        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            # Exponential backoff: 5s, 10s, 20s, 40s, 80s
            delay = self.reconnect_delay * (2 ** (self.reconnect_attempts - 1))
            logger.info(f"🔄 Reconnect attempt {self.reconnect_attempts}/{self.max_reconnect_attempts} in {delay}s...")

            import threading
            threading.Thread(target=self._delayed_reconnect, args=(delay,), daemon=True).start()
        else:
            logger.error(f"❌ Max reconnect attempts reached. WebSocket unavailable.")
            logger.info("🔄 Resetting reconnect counter in 60s...")
            
            # Reset counter after 60 seconds
            def reset_counter():
                import time
                time.sleep(60)
                self.reconnect_attempts = 0
                logger.info("✅ Reconnect counter reset, will try again on next connect attempt")
            
            import threading
            threading.Thread(target=reset_counter, daemon=True).start()

    def _delayed_reconnect(self, delay):
        """Delayed reconnect with specified delay"""
        import time
        time.sleep(delay)
        self.connect()
    
    def _on_open(self, ws):
        """Called when connection is opened"""
        logger.info("✅ WebSocket Connected!")
        logger.info(f"📊 Connection state: is_connected={self.is_connected}")
        self.is_connected = True
        self.reconnect_attempts = 0  # Reset on successful connect

        # Subscribe to channels
        logger.info(f"📋 Subscribing to {len(self.subscribed_channels)} channels...")
        for channel in self.subscribed_channels:
            logger.info(f"📡 Subscribing to channel: {channel}")
            self.subscribe(channel, use_auth=self._is_private_channel(channel))

        # Notify callback
        if self.on_connect_callback:
            self.on_connect_callback()
    
    def _is_private_channel(self, channel):
        """Check if channel requires authentication"""
        private_channels = ['user_trades', 'user_orders', 'user_balance']
        return any(pc in channel for pc in private_channels)
    
    def subscribe(self, channel, use_auth=False):
        """Subscribe to a channel with correct Indodax format"""
        if channel not in self.subscribed_channels:
            self.subscribed_channels.add(channel)

            # Indodax WebSocket subscription format
            # method: 1 for subscribe
            # id: unique request ID
            message = {
                "method": 1,
                "params": {
                    "channel": channel
                },
                "id": int(time.time() * 1000)  # Unique request ID
            }

            self._send_message(message)
            logger.info(f"📡 Subscribed to {channel} (Indodax format)")
    
    def _create_auth_message(self, channel):
        """Create authenticated subscription message"""
        timestamp = str(int(time.time() * 1000))
        message = f"GET/{channel}/{timestamp}"
        
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        return {
            "method": "subscribe",
            "channel": channel,
            "auth": {
                "apikey": self.api_key,
                "signature": signature,
                "timestamp": timestamp
            }
        }
    
    def _send_message(self, message):
        """Send message to WebSocket with logging"""
        if self.is_connected and self.ws:
            try:
                msg_str = json.dumps(message)
                logger.info(f"📤 Sending: {msg_str}")
                self.ws.send(msg_str)
                logger.info(f"✅ Message sent successfully")
            except Exception as e:
                logger.error(f"❌ Failed to send message: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
        else:
            logger.error(f"❌ Cannot send message: is_connected={self.is_connected}, ws={self.ws is not None}")
    
    def _on_message(self, ws, message):
        """Called when message is received"""
        try:
            # Log ALL raw messages for debugging (first 300 chars)
            logger.info(f"📥 Raw WS message ({len(message)} chars): {message[:300]}")
            
            data = json.loads(message)

            if self.on_message_callback:
                self.on_message_callback(data)

        except Exception as e:
            logger.error(f"❌ Message handling error: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    def _on_error(self, ws, error):
        logger.error(f"⚠️ WebSocket Error: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """Called when connection closes"""
        logger.info(f"❌ WebSocket Closed: code={close_status_code}, msg={close_msg}")
        logger.info(f"📊 Connection state: is_connected={self.is_connected}, reconnect_attempts={self.reconnect_attempts}")
        self.is_connected = False

        # Attempt reconnect
        self._schedule_reconnect()
    
    def _run_ws(self):
        self.ws.run_forever()
    
    def disconnect(self):
        if self.ws:
            self.ws.close()
        logger.info("👋 WebSocket Disconnected")
