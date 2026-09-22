# Tujuan: Membuat chart ringkas untuk lampiran Telegram tanpa menyentuh logika sinyal.
# Caller: bot.AdvancedCryptoBot.get_signal.
# Dependensi: matplotlib, pandas-like dataframe.
# Main Functions: build_signal_chart_image.
# Side Effects: none (mengembalikan BytesIO).

from io import BytesIO
import os


os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")


def _has_useful_price_movement(prices):
    """Return True when a chart has enough real movement to avoid flat/synthetic output."""
    try:
        prices = prices.dropna().astype(float)
    except Exception:
        return False
    if len(prices) < 3:
        return False
    min_price = float(prices.min())
    max_price = float(prices.max())
    last_price = abs(float(prices.iloc[-1]))
    if last_price <= 0:
        return False
    return ((max_price - min_price) / last_price) >= 0.0001


def build_signal_chart_image(pair, df, signal=None, max_points=80):
    """Return a PNG BytesIO chart for a signal, or None if data is insufficient/usefully flat."""
    if df is None or getattr(df, "empty", True):
        return None

    required_cols = {"close"}
    if not required_cols.issubset(set(df.columns)):
        return None

    chart_df = df.tail(max_points).copy()
    if chart_df.empty:
        return None

    prices = chart_df["close"].astype(float)
    if not _has_useful_price_movement(prices):
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x_values = range(len(chart_df))
    sma20 = prices.rolling(window=20, min_periods=1).mean()

    fig, ax = plt.subplots(figsize=(7.2, 3.8), dpi=140)
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#111827")

    ax.plot(x_values, prices, color="#38bdf8", linewidth=1.8, label="Price")
    ax.plot(x_values, sma20, color="#facc15", linewidth=1.1, alpha=0.9, label="SMA20")

    recommendation = (signal or {}).get("recommendation", "HOLD")
    marker_color = "#22c55e" if recommendation in ("BUY", "STRONG_BUY") else "#ef4444"
    if recommendation not in ("BUY", "STRONG_BUY", "SELL", "STRONG_SELL"):
        marker_color = "#facc15"
    ax.scatter([len(chart_df) - 1], [prices.iloc[-1]], color=marker_color, s=42, zorder=5)

    ax.set_title(f"{pair.upper()} Signal Chart", color="#f8fafc", fontsize=12, pad=10)
    ax.tick_params(axis="both", colors="#cbd5e1", labelsize=8)
    ax.grid(True, color="#334155", alpha=0.45, linewidth=0.6)
    for spine in ax.spines.values():
        spine.set_color("#334155")

    legend = ax.legend(loc="upper left", fontsize=8, frameon=True)
    legend.get_frame().set_facecolor("#1f2937")
    legend.get_frame().set_edgecolor("#334155")
    for text in legend.get_texts():
        text.set_color("#e5e7eb")

    fig.tight_layout()
    image = BytesIO()
    fig.savefig(image, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    image.seek(0)
    image.name = f"{pair.lower()}_signal_chart.png"
    return image
