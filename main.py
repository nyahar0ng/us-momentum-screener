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
    import yfinance as yf

    tqqq_capital    = capital * 0.5
    momentum_capital = capital * 0.5
    per_stock       = momentum_capital / TOTAL_STOCKS

    # TQQQの前日終値を取得
    tqqq_data  = yf.download("TQQQ", period="2d", auto_adjust=True, progress=False)
    tqqq_close = float(tqqq_data["Close"].iloc[-1].item()) if not tqqq_data.empty else 0

    print("\n" + "=" * 60)
    print(f"  発注リスト  （総資金: ${capital:,.2f}）")
    print(f"  TQQQ 50%: ${tqqq_capital:,.2f}  /  モメンタム株 50%: ${momentum_capital:,.2f} ÷ {TOTAL_STOCKS}銘柄 = ${per_stock:,.2f}/銘柄")
    print("=" * 60)
    print(f"  {'銘柄':<14}  {'前日終値':>10}  {'発注株数':>10}  {'想定金額':>12}  {'割合':>6}")
    print("  " + "-" * 62)

    total_estimated = 0.0

    # TQQQ
    if tqqq_close > 0:
        tqqq_qty       = round(tqqq_capital / tqqq_close, 2)
        tqqq_estimated = round(tqqq_qty * tqqq_close, 2)
        total_estimated += tqqq_estimated
        print(f"  {'TQQQ':<14}  ${tqqq_close:>9.2f}  {tqqq_qty:>10.2f}株  ${tqqq_estimated:>11,.2f}  {'50.0%':>6}")
    else:
        print(f"  {'TQQQ':<14}  前日終値取得不可 → 手動確認")

    print("  " + "-" * 62)

    # モメンタム株
    for ticker in target_tickers:
        close = prev_closes.get(ticker, 0)
        if close <= 0:
            print(f"  {ticker:<14}  前日終値取得不可 → 手動確認")
            continue
        qty           = round(per_stock / close, 2)
        estimated     = round(qty * close, 2)
        ratio         = estimated / capital * 100
        total_estimated += estimated
        print(f"  {ticker:<14}  ${close:>9.2f}  {qty:>10.2f}株  ${estimated:>11,.2f}  {ratio:>5.1f}%")

    print("  " + "-" * 62)
    print(f"  {'合計':<14}  {'':>10}  {'':>10}  ${total_estimated:>11,.2f}  {'100.0%':>6}")
    print(f"  残余現金（端数）: ${capital - total_estimated:,.2f}")
    print("=" * 60)
    print("\n  ※ 上記は前日終値ベースの概算です。寄り付き成り行きの約定価格とは異なります。")
    print("  ※ 発注は手動で行ってください。\n")

    logger.info("選定・出力完了")

    # ── STEP 7: portfolio.json を更新（トラッカー用）────
    import json
    holdings = {"TQQQ": tqqq_qty if tqqq_close > 0 else 0}
    for ticker in target_tickers:
        close = prev_closes.get(ticker, 0)
        if close > 0:
            holdings[ticker] = round(per_stock / close, 2)

    portfolio_data = {
        "start_date":       datetime.today().strftime("%Y-%m-%d"),
        "initial_capital":  capital,
        "holdings":         holdings,
    }
    with open("portfolio.json", "w") as f:
        json.dump(portfolio_data, f, indent=2, ensure_ascii=False)
    logger.info("portfolio.json を更新しました（トラッカー用）")


if __name__ == "__main__":
    main()
