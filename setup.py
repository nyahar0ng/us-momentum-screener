#!/usr/bin/env python3
# ============================================================
# setup.py  –  portfolio.json の初期生成
#
# 初回のみ手動でActions上から実行する。
# 仮想元本 INITIAL_CAPITAL をもとに、当日終値で株数を計算して
# portfolio.json を生成する。
# ============================================================

import json
from datetime import datetime

import pandas as pd
import yfinance as yf

from universe import get_sp500_tickers
from momentum import fetch_all_returns, select_portfolio, flatten_portfolio
from config import TOTAL_STOCKS

INITIAL_CAPITAL = 10000  # 仮想元本（ドル）


def get_prices(tickers: list[str]) -> dict[str, float]:
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


def main():
    print("=== Setup: portfolio.json 生成 ===")
    print(f"仮想元本: ${INITIAL_CAPITAL:,}")

    # 銘柄選定
    tickers    = get_sp500_tickers()
    returns_df = fetch_all_returns(tickers)
    portfolio  = select_portfolio(returns_df)
    target     = flatten_portfolio(portfolio)

    # 価格取得
    tqqq_raw   = yf.download("TQQQ", period="5d", auto_adjust=True, progress=False)
    tqqq_close = float(tqqq_raw["Close"].iloc[-1].item()) if not tqqq_raw.empty else 0

    all_prices = get_prices(target)

    # 株数計算
    tqqq_capital    = INITIAL_CAPITAL * 0.5
    momentum_capital = INITIAL_CAPITAL * 0.5
    per_stock       = momentum_capital / TOTAL_STOCKS

    holdings = {}

    if tqqq_close > 0:
        holdings["TQQQ"] = round(tqqq_capital / tqqq_close, 2)

    for ticker in target:
        price = all_prices.get(ticker, 0)
        if price > 0:
            holdings[ticker] = round(per_stock / price, 2)

    # portfolio.json 書き出し
    data = {
        "start_date":      datetime.today().strftime("%Y-%m-%d"),
        "initial_capital": INITIAL_CAPITAL,
        "holdings":        holdings,
    }
    with open("portfolio.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("\n選定銘柄と株数:")
    for ticker, qty in holdings.items():
        price = all_prices.get(ticker, tqqq_close if ticker == "TQQQ" else 0)
        print(f"  {ticker:<14} {qty:>8.2f}株  @ ${price:.2f}")

    print(f"\nportfolio.json を生成しました（元本: ${INITIAL_CAPITAL:,}）")


if __name__ == "__main__":
    main()
