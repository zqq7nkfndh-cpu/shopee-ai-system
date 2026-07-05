# AI副業運用システム(楽天ROOM / note / Shopee)

トレンド調査・商品リサーチ・投稿文/出品下書き作成・収益管理を半自動化するローカルPythonツールです。
**「最終的な投稿・出品・価格決定は必ず人間が行う」ことを前提に設計しています。**

## 0. できること / できないこと

| できること | できないこと(意図的に実装していません) |
|---|---|
| 楽天ランキングAPIを使ったトレンド商品リサーチ | 楽天ROOMへの自動投稿・自動コメント |
| 楽天ROOM投稿文の下書き(3パターン)+ハッシュタグ生成 | 楽天商品画像の保存・加工・再アップロード |
| Shopee向け利益計算・英語コピー・出品下書きCSV生成 | Shopeeへの完全自動出品 |
| 薬機法/景品表示法/輸出規制/商標リスクの簡易チェック | 出品可否の法的な最終判断(必ず人間・専門家が確認) |
| noteメンバーシップ向け週次実験ログの下書き生成 | AI量産的な誇大レポートの自動公開 |

## 1. セットアップ

```bash
cd ai_side_biz
python -m venv venv
source venv/bin/activate   # Windowsは venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# .env を開いて RAKUTEN_APP_ID などを入力(未入力でもサンプルデータで動作確認可能)
```

## 2. 実行方法

```bash
# 楽天ROOMリサーチ + 投稿文下書き生成
python main.py rakuten --genre-ids 100371,100804

# Shopee出品下書き生成(目標利益率30%の例)
python main.py shopee --target-margin 0.3

# note週次レポート下書き生成
python main.py note

# 全体を統合したdashboard.csvを更新
python main.py dashboard

# 全部まとめて実行
python main.py all
```

出力先はすべて `outputs/` フォルダです。

- `outputs/rakuten_room_candidates.csv`
- `outputs/shopee_listing_drafts.csv`
- `outputs/note_weekly_report.md`
- `outputs/dashboard.csv`

## 3. 運用フロー(推奨)

### 楽天ROOM
1. `python main.py rakuten` を実行
2. `rakuten_room_candidates.csv` の `room_text` 列(3パターン+ハッシュタグ)を確認
3. `risk_level` が medium/high の商品は特に内容を精査する
4. 気に入った投稿文を**人間が手動で**楽天ROOMアプリ/サイトから投稿する
5. 商品画像は楽天が提供するROOM投稿機能(商品ページからの投稿)を使い、画像の保存・加工・再アップロードはしない

### Shopee
1. Shopeeアプリ/サイトで気になる国別の売れ筋を見つけたら、`data/shopee_trend_input.csv` に手入力
   (テンプレートは `data/shopee_trend_input_template.csv` をコピーして使う)
2. `python main.py shopee` を実行 → `shopee_listing_drafts.csv` が更新される
3. `risk_level` が high の行は出品しない、または内容を大きく見直す
4. 出品してよいと判断した行だけ、CSVを開いて `approved` 列を `TRUE` に手動で変更する
5. `approved=TRUE` かつ内容確認済みの行だけを、Shopee Seller Centerから**人間が手動で**出品する
   (本システムには自動出品機能は実装していません)

### note
1. 週1回、`data/weekly_results.json` に実際の投稿数・注文数・収益・失敗・改善点を記入
   (テンプレートは `data/weekly_results_template.json`)
2. `python main.py note` を実行 → `note_weekly_report.md` が生成される
3. 生成された下書きに**自分の言葉・実体験**を加筆修正してから公開する
   (煽り文句や誇大な収益アピールを追加しないこと)

### dashboard
- `python main.py dashboard` で楽天ROOM・Shopeeの候補を統合した一覧を更新
- 既存の `approved` / `status` は保持されるので、承認作業をやり直す必要はない

## 4. CSV共通スキーマ

```
date, platform, country, genre, product_name, source_url,
trend_reason, season_reason, target_customer,
cost_price, selling_price, shipping_cost, fee_estimate, profit, profit_margin,
risk_level, risk_reason,
room_text, shopee_title, shopee_description,
note_angle, status, approved
```

## 5. リスクチェックについて

`risk_checker.py` はキーワードベースの簡易チェックです。以下を機械的に検出します。

- 薬機法・景品表示法に触れやすい誇大・断定表現
- 食品・化粧品・サプリメント・電池・液体などの規制されやすいカテゴリ
- ブランド品・商標権侵害の疑い

**このチェックだけで出品/投稿の可否を最終判断しないでください。** 疑わしい場合は
薬機法アドバイザー・弁護士・通関業者・各プラットフォームの公式ガイドラインを確認してください。

## 6. カスタマイズポイント

- `config.py` の `SEASON_EVENTS`: 季節・イベントキーワードを自分の得意ジャンルに合わせて調整
- `rakuten_research.py` の `DEFAULT_GENRE_IDS`: 楽天ジャンルIDを運用したいジャンルに変更
- `shopee_research.py` の `TRANSACTION_FEE_RATE` 等: Shopeeの最新手数料に合わせて調整
- `note_generator.py`: 記事の見出し構成やトーンを自分のnoteのスタイルに合わせて調整

## 7. 免責事項

本システムは業務効率化のための補助ツールです。生成される投稿文・出品文・リスク判定・
利益計算は目安であり、正確性を保証するものではありません。実際の投稿・出品・価格設定・
法令遵守については、必ず利用者自身の責任で最終確認を行ってください。
