import pandas as pd

from analysis.transformer_explorer import build_sequence_snapshot, snapshot_to_features


def test_build_sequence_snapshot_returns_usable_features():
    df = pd.DataFrame({
        "close": [100 + i for i in range(80)],
        "volume": [1000 + (i % 5) * 10 for i in range(80)],
    })

    snapshot = build_sequence_snapshot(df, pair="testidr", sequence_length=60)
    features = snapshot_to_features(snapshot)

    assert snapshot.usable is True
    assert features["pair"] == "testidr"
    assert features["sequence_length"] == 60
    assert features["trend_slope_pct"] > 0


def test_build_sequence_snapshot_fails_safe_on_insufficient_data():
    df = pd.DataFrame({"close": [100, 101]})

    snapshot = build_sequence_snapshot(df, pair="testidr", sequence_length=60)

    assert snapshot.usable is False
    assert "insufficient" in snapshot.reason
