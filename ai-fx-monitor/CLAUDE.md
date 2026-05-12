# CLAUDE.md

AI開発パートナーへの指示書

---

## このプロジェクトの目的

FX市場を監視し、「買い候補」「売り候補」「見送り」を根拠付きで提示するシステムです。
最終判断は必ず人間が行います。自動売買・本番注文機能は実装しません。

---

## 絶対に守るルール

### 実装禁止事項（いかなる理由があっても）

1. **本番注文機能を作らない**
2. **ライブ口座に接続しない**
3. **承認ボタンから注文処理に繋げない**
4. **損切りなし・ナンピン・マーチンゲール戦略を実装しない**
5. **人間承認なしで発注に進む設計にしない**
6. **APIキーをコードに直接書かない（.envを使う）**

### AIコメント生成の制約

- AIコメントはルール判定を勝手に変更してはいけない
- 「買い候補」と判定されたものを「見送り」に変えてはいけない（逆も同様）
- AIは補足説明のみを行う
- 以下の表現は絶対に使わない：
  - 「絶対に勝てる」「必ず上がる」「必ず下がる」
  - 「今すぐ全力」「損切り不要」
  - 「ナンピン推奨」「マーチンゲール推奨」
  - 「儲かる」「勝率100%」「放置で稼げる」

---

## 開発時のルール

1. 大きな変更前には必ず計画を説明する
2. ファイル削除は勝手にしない
3. 既存ファイルの上書きは確認する
4. 変更したファイル一覧を最後に報告する
5. テストを作れる箇所はテストを作る
6. 動作確認コマンドをREADMEに書く
7. エラーが出たら原因と修正内容をPROGRESS.mdに残す
8. 実装が途中で止まっても、次に再開しやすいようにPROGRESS.mdを更新する
9. 金融取引の安全性を最優先にする
10. 便利さよりも、暴走しない設計を優先する

---

## アーキテクチャ方針

### データフロー

```
CSVデータ → loader.py → resampler.py → indicators/ → strategy/ → market_analyzer.py → Web画面
```

### 将来の拡張ポイント（アダプター設計）

```python
# 価格取得アダプター（現在はCSV、将来はOANDA）
class PriceDataAdapter(Protocol):
    def get_ohlcv(self, symbol: str, timeframe: str) -> pd.DataFrame: ...

# 通知アダプター（将来はLINE/Slack/メール）
class NotificationAdapter(Protocol):
    def send(self, message: str) -> bool: ...

# 注文アダプター（将来はデモのみ、本番は絶対に分離）
class OrderAdapter(Protocol):
    def place_demo_order(self, ...) -> OrderResult: ...
    # place_live_order は実装しない
```

### 判定ルールの変更方法

`app/strategy/rules.py` の `BUY_CONDITIONS` / `SELL_CONDITIONS` を変更するだけです。
ルールはデータクラスで定義されており、コアロジックには影響しません。

---

## ファイル構成の意図

| ファイル | 役割 | 変更頻度 |
|----------|------|----------|
| strategy/rules.py | 売買ルール定義 | 高（チューニング時） |
| strategy/scoring.py | スコア計算 | 中 |
| strategy/risk.py | 損切り・利確計算 | 中 |
| indicators/ | テクニカル指標 | 低 |
| services/market_analyzer.py | 全体統合 | 低 |
| services/ai_commentary.py | コメント生成 | 低（API切替時） |
| database/ | 永続化 | 低 |
| web/ | 画面表示 | 中（UI改善時） |

---

## テスト方針

```bash
python -m pytest tests/ -v
```

- 指標計算は数値の正確さをテスト
- ルール判定は境界値テストを必ず含める
- リスク計算は損切りなし状態での挙動をテスト
- データ不足時は必ず「見送り」になることをテスト

---

## 環境変数

`.env.example` を参照。本番APIキーは `TRADING_MODE=demo_only` のまま絶対に変更しないこと。

---

## 現在のフェーズ

MVP（Phase 0〜5完了）。詳細は ROADMAP.md を参照。
