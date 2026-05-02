# ============================================================
# cache_manager.py  –  価格データのディスクキャッシュ管理（yfinance版）
# ============================================================

import json
import logging
import os
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from config import LOOKBACK_DAYS

logger = logging.getLogger(__name__)

CACHE_DIR     = "cache"
PRICES_PATH   = os.path.join(CACHE_DIR, "prices.parquet")
METADATA_PATH = os.path.join(CACHE_DIR, "metadata.json")
HISTORY_DAYS  = 365 + 30  # 12ヶ月（暦日）+ バッファ


def _load_metadata() -> dict:
    if not os.path.exists(METADATA_PATH):
        return {"last_updated": None, "cached_tickers": []}
    with open(METADATA_PATH, "r") as f:
        return json.load(f)


def _save_metadata(meta: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(METADATA_PATH, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _load_prices() -> pd.DataFrame:
    if not os.path.exists(PRICES_PATH):
        return pd.DataFrame()
    df = pd.read_parquet(PRICES_PATH)
    df.index = pd.to_datetime(df.index)
    return df


def _save_prices(df: pd.DataFrame):
    os.makedirs(CACHE_DIR, exist_ok=True)
    df.to_parquet(PRICES_PATH)


def _to_yf(ticker: str) -> str:
    """US.AAPL → AAPL"""
    return ticker.replace("US.", "")


def _to_internal(ticker: str) -> str:
    """AAPL → US.AAPL"""
    return f"US.{ticker}"


def update_cache(current_tickers: list[str]) -> pd.DataFrame:
    """
    yfinance でキャッシュを更新して全価格データを返す。
    初回: 全銘柄の1年分を一括ダウンロード
    2回目以降: 前回更新日以降の差分のみダウンロード
    """
    meta         = _load_metadata()
    cached_df    = _load_prices()
    cached_set   = set(meta.get("cached_tickers", []))
    current_set  = set(current_tickers)

    today        = datetime.today()
    today_str    = today.strftime("%Y-%m-%d")
    history_start = (today - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")

    added_tickers   = list(current_set - cached_set)
    removed_tickers = list(cached_set - current_set)
    existing_tickers = list(current_set & cached_set)

    logger.info(f"キャッシュ更新: 継続={len(existing_tickers)}, 新規={len(added_tickers)}, 削除={len(removed_tickers)}")

    last_updated = meta.get("last_updated")
    if last_updated:
        diff_start = (datetime.strptime(last_updated, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        diff_start = history_start

    new_dfs = []

    # ── 既存銘柄: 差分のみ取得 ──────────────────────────────
    if existing_tickers and diff_start <= today_str:
        logger.info(f"  既存 {len(existing_tickers)} 銘柄の差分取得: {diff_start} ～ {today_str}")
        yf_tickers = [_to_yf(t) for t in existing_tickers]
        raw = yf.download(yf_tickers, start=diff_start, end=today_str,
                          auto_adjust=True, progress=False)
        df = _parse_yf(raw, existing_tickers)
        if not df.empty:
            new_dfs.append(df)

    # ── 新規銘柄: フル取得 ────────────────────────────────────
    if added_tickers:
        logger.info(f"  新規 {len(added_tickers)} 銘柄をフル取得: {history_start} ～ {today_str}")
        yf_tickers = [_to_yf(t) for t in added_tickers]
        raw = yf.download(yf_tickers, start=history_start, end=today_str,
                          auto_adjust=True, progress=False)
        df = _parse_yf(raw, added_tickers)
        if not df.empty:
            new_dfs.append(df)

    # ── マージ ───────────────────────────────────────────────
    if new_dfs:
        new_df = pd.concat(new_dfs)
        if not cached_df.empty:
            combined = pd.concat([cached_df.reset_index(), new_df.reset_index()])
            combined = combined.drop_duplicates(subset=["date", "ticker"], keep="last")
        else:
            combined = new_df.reset_index()

        if removed_tickers:
            combined = combined[~combined["ticker"].isin(removed_tickers)]

        cutoff = today - timedelta(days=HISTORY_DAYS)
        combined = combined[pd.to_datetime(combined["date"]) >= cutoff]
        combined = combined.sort_values(["date", "ticker"]).set_index("date")
        _save_prices(combined)
        final_df = combined
    else:
        if not cached_df.empty and removed_tickers:
            tmp = cached_df.reset_index()
            tmp = tmp[~tmp["ticker"].isin(removed_tickers)].set_index("date")
            _save_prices(tmp)
            final_df = tmp
        else:
            final_df = cached_df

    _save_metadata({"last_updated": today_str, "cached_tickers": list(current_set)})
    logger.info(f"キャッシュ更新完了 → {PRICES_PATH}")
    return final_df


def _parse_yf(raw: pd.DataFrame, internal_tickers: list[str]) -> pd.DataFrame:
    """
    yfinance のダウンロード結果を (date, ticker, close, volume, turnover) 形式に変換する
    """
    if raw.empty:
        return pd.DataFrame()

    records = []
    for internal in internal_tickers:
        yf_ticker = _to_yf(internal)
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                close  = raw["Close"][yf_ticker].dropna()
                volume = raw["Volume"][yf_ticker].dropna()
            else:
                # 銘柄が1つの場合はMultiIndexにならない
                close  = raw["Close"].dropna()
                volume = raw["Volume"].dropna()

            df = pd.DataFrame({
                "date":     close.index,
                "ticker":   internal,
                "close":    close.values,
                "volume":   volume.reindex(close.index).values,
            })
            df["turnover"] = df["close"] * df["volume"]
            records.append(df)
        except (KeyError, Exception):
            continue

    if not records:
        return pd.DataFrame()

    result = pd.concat(records, ignore_index=True)
    result["date"] = pd.to_datetime(result["date"])
    return result.set_index("date")
