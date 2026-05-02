# ============================================================
# universe.py  –  S&P 500 構成銘柄ユニバースの取得
# ============================================================

import io
import logging
import urllib.request

import pandas as pd

logger = logging.getLogger(__name__)

_TICKER_FIX = {
    "BRK.B": "BRK-B",
    "BRK.A": "BRK-A",
    "BF.B":  "BF-B",
    "BF.A":  "BF-A",
}


def get_sp500_tickers() -> list[str]:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    logger.info("S&P 500 構成銘柄をWikipediaから取得中...")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    with urllib.request.urlopen(req) as resp:
        html = resp.read()

    tables = pd.read_html(io.BytesIO(html))
    sp500_df = tables[0]
    raw_tickers = sp500_df["Symbol"].tolist()

    moomoo_tickers = []
    for ticker in raw_tickers:
        ticker = str(ticker).strip()
        ticker = _TICKER_FIX.get(ticker, ticker)
        moomoo_tickers.append(f"US.{ticker}")

    logger.info(f"{len(moomoo_tickers)} 銘柄のユニバースを取得しました")
    return moomoo_tickers
