#!/usr/bin/env python3
# ============================================================
# tracker.py  –  日次パフォーマンス記録 & グラフ生成（騰落率表示）
# ============================================================

import json
import os
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

PORTFOLIO_PATH   = "portfolio.json"
PERFORMANCE_PATH = "data/performance.csv"
CHART_PATH       = "docs/index.html"


def load_portfolio() -> dict:
    if not os.path.exists(PORTFOLIO_PATH):
        raise FileNotFoundError(
            f"{PORTFOLIO_PATH} が見つかりません。"
            "main.py を実行してリバランスを記録してください。"
        )
    with open(PORTFOLIO_PATH, "r") as f:
        return json.load(f)


def load_performance() -> pd.DataFrame:
    if not os.path.exists(PERFORMANCE_PATH):
        return pd.DataFrame(columns=["date", "portfolio_return", "qld_return"])
    df = pd.read_csv(PERFORMANCE_PATH)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"])


def save_performance(df: pd.DataFrame):
    os.makedirs("data", exist_ok=True)
    df.to_csv(PERFORMANCE_PATH, index=False)


def get_latest_prices(tickers: list[str]) -> dict[str, float]:
    yf_tickers = [t.replace("US.", "") for t in tickers]
    raw = yf.download(yf_tickers, period="5d", auto_adjust=True, progress=False)
    prices = {}
    for internal, yf_t in zip(tickers, yf_tickers):
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                series = raw["Close"][yf_t].dropna()
            else:
                series = raw["Close"].dropna()
            if not series.empty:
                prices[internal] = float(series.iloc[-1])
        except Exception:
            pass
    return prices


def calc_portfolio_value(holdings: dict[str, float], prices: dict[str, float]) -> float:
    total = 0.0
    for ticker, qty in holdings.items():
        price = prices.get(ticker, prices.get(f"US.{ticker}", 0))
        total += qty * price
    return total


def generate_chart(df: pd.DataFrame):
    os.makedirs("docs", exist_ok=True)

    latest_port = df["portfolio_return"].iloc[-1]
    latest_qld  = df["qld_return"].iloc[-1]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["portfolio_return"],
        name="TQQQ 50% + Momentum 50%",
        line=dict(color="#00b4d8", width=2),
    ))

    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["qld_return"],
        name="QLD 100%",
        line=dict(color="#f77f00", width=2),
    ))

    fig.add_hline(y=0, line_dash="dot", line_color="gray", annotation_text="±0%")

    fig.update_layout(
        title=f"パフォーマンス比較  |  TQQQ50+Mom: {latest_port:+.1f}%  |  QLD: {latest_qld:+.1f}%",
        xaxis_title="日付",
        yaxis_title="騰落率 (%)",
        yaxis_ticksuffix="%",
        hovermode="x unified",
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    fig.write_html(CHART_PATH, include_plotlyjs="cdn")
    print(f"グラフ更新: {CHART_PATH}")


def main():
    today_str = datetime.today().strftime("%Y-%m-%d")
    print(f"=== Daily Tracker: {today_str} ===")

    port            = load_portfolio()
    initial_capital = port["initial_capital"]
    holdings        = port["holdings"]
    perf_df         = load_performance()

    if not perf_df.empty and perf_df["date"].dt.strftime("%Y-%m-%d").iloc[-1] == today_str:
        print("本日分はすでに記録済みです。グラフを再生成します。")
        generate_chart(perf_df)
        return

    all_tickers = list(holdings.keys()) + ["QLD"]
    prices      = get_latest_prices(all_tickers)

    # ポートフォリオ騰落率
    port_value      = calc_portfolio_value(holdings, prices)
    portfolio_return = (port_value / initial_capital - 1) * 100

    # QLD騰落率（初日の終値を基準に正規化）
    qld_price_today = prices.get("QLD", 0)
    if perf_df.empty:
        port["qld_start_price"] = qld_price_today
        with open(PORTFOLIO_PATH, "w") as f:
            json.dump(port, f, indent=2)
        qld_return = 0.0
    else:
        qld_start_price = port.get("qld_start_price", qld_price_today)
        qld_return = (qld_price_today / qld_start_price - 1) * 100 if qld_start_price > 0 else 0.0

    print(f"  ポートフォリオ: {portfolio_return:+.2f}%")
    print(f"  QLD:            {qld_return:+.2f}%")

    new_row = pd.DataFrame([{
        "date":             today_str,
        "portfolio_return": round(portfolio_return, 4),
        "qld_return":       round(qld_return, 4),
    }])
    perf_df = pd.concat([perf_df, new_row], ignore_index=True)
    save_performance(perf_df)
    generate_chart(perf_df)
    print("完了")


if __name__ == "__main__":
    main()
