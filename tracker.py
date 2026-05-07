#!/usr/bin/env python3
# ============================================================
# tracker.py  –  日次パフォーマンス記録 & グラフ生成
#
# 毎日マーケットクローズ後にGitHub Actionsで実行される。
# portfolio.json の保有株数 × 終値 でポートフォリオ価値を計算し、
# QLD100%保有の場合と比較してグラフを更新する。
# ============================================================

import json
import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

PORTFOLIO_PATH  = "portfolio.json"
PERFORMANCE_PATH = "data/performance.csv"
CHART_PATH      = "docs/index.html"


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
        return pd.DataFrame(columns=["date", "portfolio_value", "qld_value"])
    return pd.read_csv(PERFORMANCE_PATH, parse_dates=["date"])


def save_performance(df: pd.DataFrame):
    os.makedirs("data", exist_ok=True)
    df.to_csv(PERFORMANCE_PATH, index=False)


def get_latest_prices(tickers: list[str]) -> dict[str, float]:
    """前日終値を取得する"""
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


def generate_chart(df: pd.DataFrame, initial_capital: float):
    os.makedirs("docs", exist_ok=True)

    fig = go.Figure()

    # ポートフォリオ（TQQQ50%+モメンタム株50%）
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["portfolio_value"],
        name="TQQQ 50% + Momentum 50%",
        line=dict(color="#00b4d8", width=2),
    ))

    # QLD 100%
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["qld_value"],
        name="QLD 100%",
        line=dict(color="#f77f00", width=2),
    ))

    # 元本ライン
    fig.add_hline(
        y=initial_capital,
        line_dash="dot",
        line_color="gray",
        annotation_text="元本",
    )

    # 騰落率を計算してタイトルに表示
    if len(df) > 1:
        port_ret = (df["portfolio_value"].iloc[-1] / initial_capital - 1) * 100
        qld_ret  = (df["qld_value"].iloc[-1]  / initial_capital - 1) * 100
        title = (
            f"パフォーマンス比較  "
            f"| TQQQ50+Mom: {port_ret:+.1f}%  "
            f"| QLD: {qld_ret:+.1f}%"
        )
    else:
        title = "パフォーマンス比較"

    fig.update_layout(
        title=title,
        xaxis_title="日付",
        yaxis_title="資産額 ($)",
        hovermode="x unified",
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    fig.write_html(CHART_PATH, include_plotlyjs="cdn")
    print(f"グラフ更新: {CHART_PATH}")


def main():
    today_str = datetime.today().strftime("%Y-%m-%d")
    print(f"=== Daily Tracker: {today_str} ===")

    # ── ポートフォリオ読み込み ───────────────────────────
    port = load_portfolio()
    initial_capital = port["initial_capital"]
    start_date      = port["start_date"]
    holdings        = port["holdings"]   # {"TQQQ": qty, "US.INTC": qty, ...}

    # ── 過去データ読み込み ───────────────────────────────
    perf_df = load_performance()

    # 今日すでに記録済みならスキップ
    if not perf_df.empty and perf_df["date"].dt.strftime("%Y-%m-%d").iloc[-1] == today_str:
        print("本日分はすでに記録済みです。グラフを再生成します。")
        generate_chart(perf_df, initial_capital)
        return

    # ── 現在価格取得 ─────────────────────────────────────
    all_tickers = list(holdings.keys()) + ["QLD"]
    prices = get_latest_prices(all_tickers)

    # ── ポートフォリオ価値計算 ───────────────────────────
    port_value = calc_portfolio_value(holdings, prices)

    # ── QLD価値計算（初日の終値を基準に正規化）──────────
    qld_price_today = prices.get("QLD", 0)

    if perf_df.empty:
        # 初日: QLD の価値 = 元本（同じ金額でスタート）
        qld_start_price = qld_price_today
        port["qld_start_price"] = qld_start_price
        with open(PORTFOLIO_PATH, "w") as f:
            json.dump(port, f, indent=2)
        qld_value = initial_capital
    else:
        qld_start_price = port.get("qld_start_price", qld_price_today)
        qld_value = initial_capital * (qld_price_today / qld_start_price) if qld_start_price > 0 else initial_capital

    print(f"  ポートフォリオ価値: ${port_value:,.2f}  （元本比: {port_value/initial_capital*100-100:+.1f}%）")
    print(f"  QLD価値:            ${qld_value:,.2f}  （元本比: {qld_value/initial_capital*100-100:+.1f}%）")

    # ── パフォーマンスCSV更新 ────────────────────────────
    new_row = pd.DataFrame([{
        "date":            today_str,
        "portfolio_value": round(port_value, 2),
        "qld_value":       round(qld_value, 2),
    }])
    perf_df = pd.concat([perf_df, new_row], ignore_index=True)
    save_performance(perf_df)

    # ── グラフ生成 ───────────────────────────────────────
    generate_chart(perf_df, initial_capital)
    print("完了")


if __name__ == "__main__":
    main()
