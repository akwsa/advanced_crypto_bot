"""Regression test untuk fix volume normalisasi di IndodaxAPI.get_ticker.

Bug: Indodax return `vol_<basecoin>` per pair (vol_btc, vol_eth, vol_ada, dst)
plus `vol_idr` (selalu ada untuk pair IDR). Sebelumnya `get_ticker` cuma cek
`vol_btc → vol → volume`, jadi semua pair non-btc tersimpan volume=0.

Akibat: 100% row di table `price_history` punya volume=0.0 (180,903 row),
ML feature volume jadi konstan = noise.

Fix: cek `vol_idr` dulu (paling konsisten, unit IDR), fallback ke
`vol_<base>`, fallback ke any `vol_*` non-zero, fallback legacy.
"""
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.indodax_api import IndodaxAPI


def _make_response(ticker_payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"ticker": ticker_payload}
    return resp


def test_volume_uses_vol_idr_when_present():
    """vol_idr is the canonical, always-present volume field — prefer it."""
    api = IndodaxAPI()
    payload = {
        "last": "100", "high": "110", "low": "90",
        "buy": "99", "sell": "101", "server_time": 1234567890,
        "vol_eth": "12.5",
        "vol_idr": "5000000000",
    }
    with patch.object(api.session, "get", return_value=_make_response(payload)):
        t = api.get_ticker("ethidr")

    assert t is not None
    assert t["volume"] == 5_000_000_000.0


def test_volume_falls_back_to_vol_basecoin_when_vol_idr_missing():
    """When vol_idr is absent or zero, fall back to vol_<base>."""
    api = IndodaxAPI()
    payload = {
        "last": "100", "high": "110", "low": "90",
        "buy": "99", "sell": "101", "server_time": 1234567890,
        "vol_ada": "744587.5",
        # no vol_idr
    }
    with patch.object(api.session, "get", return_value=_make_response(payload)):
        t = api.get_ticker("adaidr")

    assert t is not None
    assert t["volume"] == 744587.5


def test_volume_falls_back_to_any_vol_key_when_basecoin_unknown():
    """If neither vol_idr nor vol_<base> match, scan any vol_* non-zero."""
    api = IndodaxAPI()
    payload = {
        "last": "100", "high": "110", "low": "90",
        "buy": "99", "sell": "101", "server_time": 1234567890,
        "vol_weirdcoin": "42.0",  # mismatch base coin name
    }
    with patch.object(api.session, "get", return_value=_make_response(payload)):
        # pair "xyzidr" tapi vol_xyz tidak ada — scan vol_* fallback
        t = api.get_ticker("xyzidr")

    assert t is not None
    assert t["volume"] == 42.0


def test_volume_zero_when_no_vol_keys():
    """Defensive: missing all vol_* keys returns 0.0 (no crash)."""
    api = IndodaxAPI()
    payload = {
        "last": "100", "high": "110", "low": "90",
        "buy": "99", "sell": "101", "server_time": 1234567890,
    }
    with patch.object(api.session, "get", return_value=_make_response(payload)):
        t = api.get_ticker("xyzidr")

    assert t is not None
    assert t["volume"] == 0.0


def test_legacy_btc_field_still_works():
    """Backward compat: payload yang cuma punya `vol_btc` tetap jalan."""
    api = IndodaxAPI()
    payload = {
        "last": "100", "high": "110", "low": "90",
        "buy": "99", "sell": "101", "server_time": 1234567890,
        "vol_btc": "16.02",
        "vol_idr": "18208562716.0",
    }
    with patch.object(api.session, "get", return_value=_make_response(payload)):
        t = api.get_ticker("btcidr")

    assert t is not None
    # vol_idr menang (lebih konsisten antar pair)
    assert t["volume"] == 18_208_562_716.0


def test_volume_invalid_string_treated_as_zero():
    """Invalid string in vol_idr should not crash — fallback to 0.0."""
    api = IndodaxAPI()
    payload = {
        "last": "100", "high": "110", "low": "90",
        "buy": "99", "sell": "101", "server_time": 1234567890,
        "vol_idr": "not-a-number",
    }
    with patch.object(api.session, "get", return_value=_make_response(payload)):
        t = api.get_ticker("ethidr")

    assert t is not None
    assert t["volume"] == 0.0


def test_volume_pair_with_uppercase_normalized():
    """Pair input case-insensitive — base extraction tetap benar."""
    api = IndodaxAPI()
    payload = {
        "last": "100", "high": "110", "low": "90",
        "buy": "99", "sell": "101", "server_time": 1234567890,
        "vol_sol": "5694205.0",
        # no vol_idr
    }
    with patch.object(api.session, "get", return_value=_make_response(payload)):
        t = api.get_ticker("SOLIDR")

    assert t is not None
    assert t["volume"] == 5_694_205.0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
