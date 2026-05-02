#!/usr/bin/env python3
# ============================================================
# main.py  –  モメンタム銘柄選定 & 発注株数出力
# ============================================================

import logging
import sys
from datetime import datetime

from universe import get_sp500_tickers
from momentum import fetch_all_returns, select_portfolio, flatten_portfolio
from config import TOTAL_STOCKS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            f"rebalance_{datetime.today().strftime('%Y%m%d_%H%M%S')}.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info(f"  モメンタム銘柄選定 開始: {datetime.today().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # ── STEP 1: ユニバース取得 ─────────────────────────────
    logger.info("\n[STEP 1] S&P 500 構成銘柄取得")
    tickers = get_sp500_tickers()

    # ── STEP 2: キャッシュ更新 & 騰落率計算 ───────────────
    logger.info("\n[STEP 2] 価格キャッシュ更新 & 騰落率計算")
    returns_df = fetch_all_returns(tickers)

    if returns_df.empty:
        logger.error("データ取得失敗。ネットワーク接続を確認してください。")
        sys.exit(1)

    # ── STEP 3: 銘柄選定 ──────────────────────────────────
    logger.info("\n[STEP 3] 銘柄選定")
    portfolio = select_portfolio(returns_df)
    target_tickers = flatten_portfolio(portfolio)

    # ── STEP 4: 前日終値をキャッシュから取得 ───────────────
    from cache_manager import _load_prices
    prices_df = _load_prices()
    prev_closes = {}
    if not prices_df.empty:
        for ticker in target_tickers:
            rows = prices_df[prices_df["ticker"] == ticker]
            if not rows.empty:
                prev_closes[ticker] = float(rows["close"].iloc[-1])

    # ── STEP 5: 投資資金を入力 ────────────────────────────
    print("\n" + "=" * 60)
    print("  選定銘柄（発注候補）")
    print("=" * 60)
    labels = {"3M": "3ヶ月モメンタム", "6M": "6ヶ月モメンタム", "12M": "12ヶ月モメンタム"}
    for period, stocks in portfolio.items():
        print(f"\n【{labels[period]}】")
        for t in stocks:
            ret_val  = returns_df.loc[t, f"return_{period}"]
            addv     = returns_df.loc[t, "addv_20d"] / 1_000_000
            close    = prev_closes.get(t, 0)
            print(f"  {t:<14}  騰落率: {ret_val:+.1%}  ADDV: ${addv:.0f}M  前日終値: ${close:.2f}")

    print("\n" + "-" * 60)
    while True:
        try:
            raw = input("投資資金を入力してください（例: 150000）: $").strip().replace(",", "")
            capital = float(raw)
            if capital <= 0:
                raise ValueError
            break
        except ValueError:
            print("  ※ 正の数値を入力してください")

    # ── STEP 6: 発注株数の計算・出力 ─────────────────────
    per_stock = capital / TOTAL_STOCKS

    print("\n" + "=" * 60)
    print(f"  発注リスト  （投資資金: ${capital:,.2f} ÷ {TOTAL_STOCKS}銘柄 = ${per_stock:,.2f}/銘柄）")
    print("=" * 60)
    print(f"  {'銘柄':<14}  {'前日終値':>10}  {'発注株数':>10}  {'想定金額':>12}")
    print("  " + "-" * 54)

    total_estimated = 0.0
    for ticker in target_tickers:
        close = prev_closes.get(ticker, 0)
        if close <= 0:
            print(f"  {ticker:<14}  前日終値取得不可 → 手動確認")
            continue
        qty           = round(per_stock / close, 2)
        estimated     = round(qty * close, 2)
        total_estimated += estimated
        print(f"  {ticker:<14}  ${close:>9.2f}  {qty:>10.2f}株  ${estimated:>11,.2f}")

    print("  " + "-" * 54)
    print(f"  {'合計':<14}  {'':>10}  {'':>10}  ${total_estimated:>11,.2f}")
    print(f"  残余現金（端数）: ${capital - total_estimated:,.2f}")
    print("=" * 60)
    print("\n  ※ 上記は前日終値ベースの概算です。寄り付き成り行きの約定価格とは異なります。")
    print("  ※ 発注は手動で行ってください。\n")

    logger.info("選定・出力完了")


if __name__ == "__main__":
    main()
