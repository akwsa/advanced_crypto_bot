# DOCUMENTATION RULES - Coding Standards

**Last Updated:** 2026-04-30  
**Purpose:** Standar dokumentasi kode, header format, dan best practices.

---

## 📝 FILE HEADER FORMAT (MANDATORY)

**Setiap file Python HARUS memiliki header ini:**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tujuan: <ringkasan 1 kalimat apa yang dilakukan file ini>
# Caller: <siapa yang memanggil file ini, atau "entrypoint" jika main>
# Dependensi: <modul/library eksternal yang dipakai>
# Main Functions: <daftar fungsi/class utama>
# Side Effects: <DB writes, API calls, file I/O, cache mutation, dll>
"""
<Docstring lebih detail tentang modul ini>
"""
```

### Contoh Lengkap:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tujuan: Pipeline end-to-end pembentukan signal per pair.
# Caller: bot.py _generate_signal_for_pair dan background monitor.
# Dependensi: TechnicalAnalysis, ML models, SignalQualityEngine, DB/cache.
# Main Functions: generate_signal_for_pair.
# Side Effects: DB read/write signal, cache reads, CPU-heavy analysis.
"""Signal generation pipeline extracted from bot.py."""

import logging
from analysis.technical_analysis import TechnicalAnalysis
```

---

## 🔍 HEADER FIELD GUIDELINES

### 1. **Tujuan** (Purpose)
- **Format:** 1 kalimat ringkas
- **Isi:** Apa yang dilakukan file ini (high-level)
- **Good:** "Runtime helpers for signal monitoring, autotrade execution, and market-intelligence gating."
- **Bad:** "This file contains some functions."

### 2. **Caller** (Who calls this)
- **Format:** Nama modul atau "entrypoint"
- **Isi:** Siapa yang import/call modul ini
- **Good:** "bot.py price-update flow and Telegram-triggered autotrade flow."
- **Good:** "entrypoint eksekusi langsung `python3 bot.py`."
- **Bad:** "Nobody" (kalau nobody berarti file ini dead code, delete!)

### 3. **Dependensi** (Dependencies)
- **Format:** Comma-separated list
- **Isi:** External libraries + internal modules yang di-import
- **Good:** "core.config, core.utils, signals.signal_pipeline, pandas, requests."
- **Good:** "core/*, analysis/*, autotrade/*, signals/*."
- **Bad:** "Many modules" (be specific!)

### 4. **Main Functions** (Public API)
- **Format:** Comma-separated function/class names
- **Isi:** Public functions/classes yang diexport
- **Good:** "generate_signal_for_pair, format_signal_message."
- **Good:** "class TradingEngine, class RiskManager."
- **Bad:** "Everything" (list them explicitly!)

### 5. **Side Effects** (Important!)
- **Format:** Comma-separated side effects
- **Isi:** Semua non-pure operations (DB, API, file I/O, state mutation)
- **Good:** "DB read/write signal, cache reads, CPU-heavy analysis."
- **Good:** "HTTP calls to Telegram/Indodax, DB writes, trade execution."
- **Bad:** "None" (kecuali file memang pure functions)

**Why Side Effects Matter:**
- Membantu debug (cari tau kenapa DB berubah)
- Membantu testing (mock side effects)
- Membantu parallelization (avoid race conditions)

---

## 📚 DOCSTRING STANDARDS

### Module Docstring (Top of File)
```python
"""
Brief 1-liner summary.

Optional longer explanation with examples if needed.
"""
```

### Function Docstring
```python
def generate_signal_for_pair(bot, pair):
    """
    Generate comprehensive trading signal using bot dependencies.
    
    Args:
        bot: AdvancedCryptoBot instance with historical_data, ml_model, etc.
        pair: Trading pair (e.g., "btcidr")
    
    Returns:
        dict: Signal with keys: recommendation, confidence, quality_score, 
              support_1, resistance_1, reason, timestamp
    
    Side Effects:
        - Saves signal to database
        - Calls Claude API for enhancement
        - Updates signal cache
    """
```

### Class Docstring
```python
class TradingEngine:
    """
    Core trading execution engine.
    
    Handles order placement, execution, and position management.
    Integrates with Indodax API for actual trades.
    
    Attributes:
        config: Config instance
        api: IndodaxAPI instance
        db: Database instance
    """
```

---

## 🏗️ CODE STRUCTURE STANDARDS

### 1. Import Order
```python
# Standard library
import asyncio
import logging
from datetime import datetime

# Third-party libraries
import pandas as pd
import numpy as np
from telegram import Update

# Local core modules
from core.config import Config
from core.database import Database

# Local feature modules
from analysis.technical_analysis import TechnicalAnalysis
from signals.signal_pipeline import generate_signal_for_pair
```

**Order:**
1. Standard library (`import`, `from`)
2. Third-party (`pandas`, `numpy`, `telegram`, dll)
3. Local core (`core/*`)
4. Local features (`analysis/*`, `signals/*`, dll)

**Blank lines:**
- 1 blank line between import groups

### 2. Function Organization
```python
# Private helper functions first (prefix _)
def _normalize_pair(pair):
    return str(pair).lower().replace("/", "")

def _is_watched(bot, pair):
    # ...

# Public API functions last
async def generate_signal_for_pair(bot, pair):
    # ...
```

### 3. Class Organization
```python
class TradingEngine:
    """Docstring"""
    
    # 1. Class variables
    MAX_POSITIONS = 3
    
    # 2. __init__
    def __init__(self, config, api):
        self.config = config
        self.api = api
    
    # 3. Public methods
    async def execute_buy(self, pair, amount):
        # ...
    
    async def execute_sell(self, pair, amount):
        # ...
    
    # 4. Private methods (prefix _)
    def _validate_order(self, pair, amount):
        # ...
    
    def _calculate_fees(self, amount):
        # ...
```

---

## 🎯 NAMING CONVENTIONS

### Variables
```python
# Good: snake_case, descriptive
trading_pair = "btcidr"
current_price = 450000000
is_auto_trade_enabled = True

# Bad: camelCase, abbreviations, unclear
tradingPair = "btcidr"  # Wrong case
cur_pr = 450000000  # Too abbreviated
flag = True  # What flag?
```

### Functions
```python
# Good: snake_case, verb-first
def calculate_rsi(data):
    pass

async def execute_buy_order(pair, amount):
    pass

def is_signal_actionable(recommendation):
    pass

# Bad: camelCase, noun-first, unclear
def calculateRSI(data):  # Wrong case
    pass

def buy(pair, amount):  # Too short, what buy?
    pass

def signal(rec):  # Noun, not verb
    pass
```

### Classes
```python
# Good: PascalCase, noun-phrase
class TradingEngine:
    pass

class SignalQualityEngine:
    pass

class RiskManager:
    pass

# Bad: snake_case, verb, abbreviation
class trading_engine:  # Wrong case
    pass

class ExecuteTrade:  # Verb, should be noun
    pass

class SigQualEng:  # Too abbreviated
    pass
```

### Constants
```python
# Good: SCREAMING_SNAKE_CASE
MAX_POSITIONS = 3
MIN_CONFIDENCE_THRESHOLD = 0.55
ACTIONABLE_SIGNALS = {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL"}

# Bad: lowercase or camelCase
max_positions = 3
minConfidenceThreshold = 0.55
```

### Private Functions/Methods
```python
# Good: prefix _
def _normalize_pair(pair):
    pass

def _calculate_internal_metric(data):
    pass

# Bad: no prefix (looks public)
def normalize_pair(pair):  # Should be public or _normalize_pair
    pass
```

---

## 💬 COMMENT STANDARDS

### Inline Comments
```python
# Good: Explain WHY, not WHAT
signal_cache[pair] = result  # Cache 2s to avoid duplicate Claude API calls

# Bad: Explain WHAT (obvious from code)
signal_cache[pair] = result  # Set cache to result
```

### TODO Comments
```python
# TODO(username): Specific task to do
# TODO(wkagung): Add retry logic for Indodax API timeout

# FIXME: Critical bug that needs fixing
# FIXME: Race condition when multiple signals for same pair

# HACK: Temporary workaround (document why)
# HACK: Indodax API returns string "0" instead of 0, convert manually
balance = float(response["balance"] or 0)
```

### Section Comments
```python
# ============================================================
# SIGNAL GENERATION
# ============================================================

async def generate_signal_for_pair(bot, pair):
    # ...


# ============================================================
# AUTO-TRADING EXECUTION
# ============================================================

async def execute_auto_buy(bot, signal):
    # ...
```

---

## 🔒 ERROR HANDLING STANDARDS

### Always Use Specific Exceptions
```python
# Good: Specific exception
try:
    price = float(data["price"])
except (KeyError, ValueError) as e:
    logger.error(f"Invalid price data: {e}")
    return None

# Bad: Bare except
try:
    price = float(data["price"])
except:  # DON'T DO THIS!
    return None
```

### Always Log Errors
```python
# Good: Log with context
try:
    result = await api.place_order(pair, amount)
except Exception as e:
    logger.error(f"Failed to place order for {pair}: {e}", exc_info=True)
    raise

# Bad: Silent failure
try:
    result = await api.place_order(pair, amount)
except:
    pass  # DON'T DO THIS!
```

---

## 🧪 TESTING STANDARDS

### Test File Naming
```
tests/test_<module_name>.py
```

Examples:
- `tests/test_scalper_dryrun_positions.py`
- `tests/test_signal_notification_controls.py`
- `tests/test_v4_integration.py`

### Test Function Naming
```python
def test_<scenario>_<expected_result>():
    pass
```

Examples:
```python
def test_signal_generation_returns_buy_on_strong_indicators():
    # ...

def test_risk_manager_rejects_trade_when_max_positions_exceeded():
    # ...

def test_scalper_closes_position_on_take_profit_hit():
    # ...
```

### Test Structure (AAA Pattern)
```python
def test_signal_passes_quality_check():
    # Arrange: Setup
    signal = {
        "recommendation": "BUY",
        "confidence": 0.75,
        "quality_score": 85,
    }
    
    # Act: Execute
    result = is_signal_actionable(signal)
    
    # Assert: Verify
    assert result is True
```

---

## 📊 LOGGING STANDARDS

### Log Levels
```python
# DEBUG: Detailed diagnostic info (only in development)
logger.debug(f"Fetched price for {pair}: {price}")

# INFO: Confirmation of normal operation
logger.info(f"Generated signal for {pair}: {recommendation}")

# WARNING: Something unexpected but not critical
logger.warning(f"Stale price for {pair}, skipping signal")

# ERROR: Error that prevents function from completing
logger.error(f"Failed to execute buy for {pair}: {e}", exc_info=True)

# CRITICAL: System-wide failure
logger.critical("Database connection lost, shutting down")
```

### Log Format
```python
# Good: Structured, includes context
logger.info(f"Signal generated | pair={pair} rec={recommendation} conf={confidence:.2f}")

# Bad: Unstructured, missing context
logger.info("Signal generated")
```

### Use Emojis for Key Events
```python
logger.info(f"✅ Trade executed | pair={pair} amount={amount}")
logger.error(f"❌ Trade failed | pair={pair} error={e}")
logger.warning(f"⚠️ Low confidence signal | pair={pair} conf={confidence}")
logger.info(f"🚀 Auto-trading enabled")
logger.info(f"🛑 Emergency stop triggered")
```

---

## 🔄 UPDATE WORKFLOW

### When You Edit Code:

1. **Update File Header** (if dependencies/main functions change)
2. **Update Docstrings** (if function signature/behavior changes)
3. **Run Tests** (see `OPERATIONS_FLOW_ALGORITHMA.md` → Test Policy)
4. **Update Canonical Docs** (if needed):
   - Changed startup/core/DB? → Update `SYSTEM_MAP.md`
   - Changed flow/signal/trading? → Update `OPERATIONS_FLOW_ALGORITHMA.md`
   - Changed commands/callbacks? → Update `COMMAND_REFERENCE.md`
   - Changed doc standards? → Update `DOCUMENTATION_RULES.md` (this file)

### Git Commit Message Format
```
<type>: <subject>

<body (optional)>

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `refactor`: Code refactoring (no behavior change)
- `test`: Add/update tests
- `chore`: Maintenance (deps, config, etc.)

**Examples:**
```
feat: add market regime detection to signal pipeline

- Added detect_market_regime() function
- Integrated regime check into auto-trading flow
- Reject trades during CHOPPY/VOLATILE regimes

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

```
fix: scalper not closing position on take profit hit

- Fixed bug in execute_auto_sell() logic
- Added test_scalper_closes_position_on_tp()

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

```
docs: update SYSTEM_MAP for new signal quality engine

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

---

## 🚫 ANTI-PATTERNS (DON'T DO THIS!)

### 1. Magic Numbers
```python
# Bad: Magic number
if confidence > 0.55:
    pass

# Good: Named constant
MIN_CONFIDENCE = 0.55
if confidence > MIN_CONFIDENCE:
    pass
```

### 2. Long Functions (> 50 lines)
```python
# Bad: 200-line function doing everything
async def process_signal(bot, pair):
    # ... 200 lines of code ...

# Good: Break into smaller functions
async def process_signal(bot, pair):
    data = await fetch_market_data(pair)
    indicators = calculate_indicators(data)
    signal = generate_ml_signal(indicators)
    enhanced = await enhance_with_ai(signal)
    return format_signal_output(enhanced)
```

### 3. Deep Nesting (> 3 levels)
```python
# Bad: Deeply nested if/for
if auto_trade_enabled:
    if pair in auto_trade_pairs:
        if signal["recommendation"] == "BUY":
            if confidence > 0.55:
                # ...

# Good: Early returns
if not auto_trade_enabled:
    return
if pair not in auto_trade_pairs:
    return
if signal["recommendation"] != "BUY":
    return
if confidence <= 0.55:
    return
# ...
```

### 4. Mutable Default Arguments
```python
# Bad: Mutable default (shared across calls!)
def add_signal(pair, tags=[]):
    tags.append(pair)  # BUG!

# Good: Use None
def add_signal(pair, tags=None):
    if tags is None:
        tags = []
    tags.append(pair)
```

### 5. String Formatting with %
```python
# Bad: Old-style % formatting
logger.info("Signal for %s: %s" % (pair, recommendation))

# Good: f-strings (Python 3.6+)
logger.info(f"Signal for {pair}: {recommendation}")
```

### 6. Global State Mutation
```python
# Bad: Global variable mutation
CACHE = {}

def update_cache(pair, price):
    CACHE[pair] = price  # Risky!

# Good: Class-based state
class PriceCache:
    def __init__(self):
        self._cache = {}
    
    def update(self, pair, price):
        self._cache[pair] = price
```

---

## ✅ CHECKLIST SEBELUM COMMIT

```
[ ] File header lengkap & up-to-date?
[ ] Docstring ada di semua public functions/classes?
[ ] Import order correct?
[ ] Naming conventions followed?
[ ] Error handling proper (no bare except)?
[ ] Logging adequate (ERROR/WARNING/INFO)?
[ ] No magic numbers (use named constants)?
[ ] No functions > 50 lines?
[ ] No nesting > 3 levels?
[ ] Tests passing (pytest)?
[ ] Canonical docs updated (if needed)?
[ ] Git commit message clear?
```

---

## 📏 CODE METRICS TARGETS

| Metric | Target | Tool |
|--------|--------|------|
| Function length | < 50 lines | Manual review |
| Nesting depth | ≤ 3 levels | Manual review |
| Code coverage | > 70% | `pytest --cov` |
| Cyclomatic complexity | < 10 | `radon cc` |
| Maintainability index | > 65 | `radon mi` |

**Run Code Quality Checks:**
```bash
# Install tools
pip install radon pytest-cov

# Check complexity
radon cc advanced_crypto_bot/ -a

# Check maintainability
radon mi advanced_crypto_bot/

# Check test coverage
pytest --cov=advanced_crypto_bot tests/
```

---

## 📖 EXAMPLE: Perfect File

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tujuan: Risk management untuk validasi trades dan position sizing.
# Caller: autotrade.trading_engine, bot.py check_trading_opportunity.
# Dependensi: core.config, core.database, core.portfolio.
# Main Functions: class RiskManager.
# Side Effects: DB reads (portfolio, positions), logging.
"""
Risk management module for trading validation.

Provides position sizing, exposure limits, and trade validation
based on portfolio risk parameters and current market conditions.
"""

import logging
from typing import Dict, Optional

from core.config import Config
from core.database import Database
from core.portfolio import Portfolio

logger = logging.getLogger("crypto_bot")

# Risk parameters
MAX_PORTFOLIO_EXPOSURE = 0.30  # 30% max per trade
MAX_CONCURRENT_POSITIONS = 3
DEFAULT_RISK_PER_TRADE = 0.10  # 10% of capital


class RiskManager:
    """
    Validates trades and calculates position sizing based on risk parameters.
    
    Attributes:
        config: Config instance
        db: Database instance
        portfolio: Portfolio instance
    """
    
    def __init__(self, config: Config, db: Database, portfolio: Portfolio):
        """Initialize RiskManager with dependencies."""
        self.config = config
        self.db = db
        self.portfolio = portfolio
    
    def validate_trade(self, pair: str, signal: Dict) -> tuple[bool, Optional[str]]:
        """
        Validate if trade should be executed based on risk rules.
        
        Args:
            pair: Trading pair (e.g., "btcidr")
            signal: Signal dict with recommendation, confidence, etc.
        
        Returns:
            (is_valid, rejection_reason)
            - (True, None) if trade is valid
            - (False, "reason") if trade should be rejected
        
        Side Effects:
            - Reads current portfolio from DB
            - Logs validation result
        """
        # Check max concurrent positions
        open_positions = self.portfolio.get_open_positions()
        if len(open_positions) >= MAX_CONCURRENT_POSITIONS:
            reason = f"Max positions ({MAX_CONCURRENT_POSITIONS}) reached"
            logger.warning(f"⚠️ Trade rejected | pair={pair} reason={reason}")
            return False, reason
        
        # Check portfolio exposure
        total_exposure = self._calculate_total_exposure()
        if total_exposure >= MAX_PORTFOLIO_EXPOSURE:
            reason = f"Max exposure ({MAX_PORTFOLIO_EXPOSURE:.0%}) reached"
            logger.warning(f"⚠️ Trade rejected | pair={pair} reason={reason}")
            return False, reason
        
        # Check available balance
        available = self.portfolio.get_available_balance()
        if available <= 0:
            reason = "Insufficient balance"
            logger.warning(f"⚠️ Trade rejected | pair={pair} reason={reason}")
            return False, reason
        
        logger.info(f"✅ Trade validated | pair={pair}")
        return True, None
    
    def calculate_position_size(self, pair: str, price: float) -> float:
        """
        Calculate position size based on risk parameters.
        
        Args:
            pair: Trading pair
            price: Current price
        
        Returns:
            float: Position size in base currency
        
        Side Effects:
            - Reads portfolio balance
        """
        available = self.portfolio.get_available_balance()
        risk_amount = available * DEFAULT_RISK_PER_TRADE
        position_size = risk_amount / price
        
        logger.debug(f"Position size calculated | pair={pair} size={position_size:.8f}")
        return position_size
    
    def _calculate_total_exposure(self) -> float:
        """Calculate total portfolio exposure (private helper)."""
        positions = self.portfolio.get_open_positions()
        total_value = sum(p["value"] for p in positions)
        portfolio_value = self.portfolio.get_total_value()
        return total_value / portfolio_value if portfolio_value > 0 else 0.0
```

---

**Navigation:**
- Prev: `COMMAND_REFERENCE.md` (Telegram commands)
- Back to: `SYSTEM_MAP.md` (system overview)
