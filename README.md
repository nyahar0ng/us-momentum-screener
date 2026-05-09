# US Momentum Screener

S&P500構成銘柄から3・6・12ヶ月モメンタムで上位15銘柄を選定するスクリーニングツール。

## ポートフォリオ構成

- **TQQQ 50%** + **モメンタム株 50%**（15銘柄均等配分）

## 戦略

- S&P500全銘柄を対象に3ヶ月・6ヶ月・12ヶ月の騰落率を計算
- 各期間の上位5銘柄を選定（重複は3ヶ月優先で除外）
- 流動性フィルター：直近20営業日の平均売買代金 $5M 以上
- リバランスは月次

## パフォーマンスグラフ

**TQQQ50%+モメンタム株50%** vs **QLD100%** の騰落率比較

👉 https://nyahar0ng.github.io/us-momentum-screener/

毎日 8:00 JST（平日）に自動更新。

## ファイル構成

| ファイル | 役割 |
|---|---|
| `setup.py` | 初回のみ実行。銘柄選定・portfolio.json 生成 |
| `tracker.py` | 日次パフォーマンス記録・グラフ生成 |
| `config.py` | パラメータ設定 |
| `universe.py` | S&P500銘柄リスト取得 |
| `momentum.py` | 騰落率計算・銘柄選定 |
| `cache_manager.py` | 価格データのキャッシュ管理 |
| `portfolio.json` | 現在の保有株数 |
| `data/performance.csv` | 日次パフォーマンスログ |
| `docs/index.html` | パフォーマンスグラフ（GitHub Pages） |

## 自動実行

cron-job.org から GitHub Actions の `workflow_dispatch` を毎日 8:00 JST に叩いて実行。
