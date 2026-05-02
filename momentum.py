# ============================================================
# momentum.py  –  モメンタム計算・流動性フィルター・銘柄選定
# ============================================================

import logging
from datetime import datetime, timedelta

import pandas as pd

from config import LOOKBACK_DAYS, NUM_STOCKS_PER_PERIOD
from cache_manager import update_cache

logger = logging.getLogger(__name__)

LIQUIDITY_WINDOW_DAYS  = 20
LIQUIDITY_MIN_ADDV_USD = 5_000_000


def fetch_all_returns(tickers: list[str]) -> pd.DataFrame:
    logger.info("価格キャッシュを更新中...")
    prices_df = update_cache(tickers)

    if prices_df.empty:
        raise RuntimeError("価格データが取得できませんでした。")

    prices_df.index = pd.to_datetime(prices_df.index)
    today = datetime.today()
    ref_dates = {
        period: today - timedelta(days=days + 5)
        for period, days in LOOKBACK_DAYS.items()
    }

    results = {}
    for ticker in tickers:
        ticker_df = prices_df[prices_df["ticker"] == ticker].copy()
        if ticker_df.empty or len(ticker_df) < LIQUIDITY_WINDOW_DAYS:
            continue

        ticker_df = ticker_df.sort_index()
        current_price = ticker_df["close"].iloc[-1]

        returns = {}
        valid = True
        for period, ref_dt in ref_dates.items():
            past_df = ticker_df[ticker_df.index <= ref_dt]
            if past_df.empty:
                valid = False
                break
            past_price = past_df["close"].iloc[-1]
            if past_price <= 0:
                valid = False
                break
            returns[f"return_{period}"] = (current_price - past_price) / past_price

        if not valid:
            continue

        recent = ticker_df.tail(LIQUIDITY_WINDOW_DAYS)
        if "turnover" in recent.columns and recent["turnover"].sum() > 0:
            addv = recent["turnover"].mean()
        elif "volume" in recent.columns:
            addv = (recent["close"] * recent["volume"]).mean()
        else:
            addv = 0.0

        returns["addv_20d"] = addv
        results[ticker] = returns

    result_df = pd.DataFrame.from_dict(results, orient="index")
    logger.info(f"騰落率計算完了: {len(result_df)} 銘柄")
    return result_df


def apply_liquidity_filter(returns_df: pd.DataFrame) -> pd.DataFrame:
    if "addv_20d" not in returns_df.columns:
        return returns_df
    before   = len(returns_df)
    filtered = returns_df[returns_df["addv_20d"] >= LIQUIDITY_MIN_ADDV_USD].copy()
    logger.info(
        f"流動性フィルター: {before} 銘柄 → {len(filtered)} 銘柄 "
        f"（除外: {before - len(filtered)} 銘柄, 基準: ADDV >= ${LIQUIDITY_MIN_ADDV_USD:,}）"
    )
    return filtered


def select_portfolio(returns_df: pd.DataFrame) -> dict[str, list[str]]:
    filtered_df = apply_liquidity_filter(returns_df)
    N = NUM_STOCKS_PER_PERIOD
    portfolio = {}
    excluded  = set()

    for period in ["3M", "6M", "12M"]:
        col        = f"return_{period}"
        candidates = filtered_df[~filtered_df.index.isin(excluded)].copy()
        top = (
            candidates[col]
            .dropna()
            .sort_values(ascending=False)
            .head(N)
            .index.tolist()
        )
        portfolio[period] = top
        excluded.update(top)
        for t in top:
            ret_val  = filtered_df.loc[t, col]
            addv_val = filtered_df.loc[t, "addv_20d"] / 1_000_000
            logger.info(f"  [{period}] {t:<14} 騰落率: {ret_val:+.1%}  ADDV: ${addv_val:.0f}M")

    return portfolio


def flatten_portfolio(portfolio: dict[str, list[str]]) -> list[str]:
    return [t for stocks in portfolio.values() for t in stocks]
