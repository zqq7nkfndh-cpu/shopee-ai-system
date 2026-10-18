# Web公開・運用手順

このアプリは単一所有者向けです。公開先へのデプロイは今回行っていません。Docker自体はこの作業環境で利用できなかったため、コンテナビルドは未検証です。本番用Gunicornの直接起動は自動テストで確認します。

## 推奨する構成

- Python 3.12 / Gunicorn、1インスタンス、1 worker・4 threads
- アプリの前にHTTPSを提供するリバースプロキシまたはホスティングのHTTPS終端
- SQLite用の**永続的なローカルディスク**。単一ホストで使用。NFS共有・複数レプリカ・起動ごとに消えるディスクを避ける
- データボリュームとバックアップ先をコードから分離

Flask開発サーバーを公開に使用しない方針は、Flask公式の[本番デプロイガイド](https://flask.palletsprojects.com/en/stable/deploying/)に基づきます。Sites / Cloudflare WorkersにはこのSQLiteファイル構成をそのまま載せられません。必要ならD1等への永続化層の移植が別作業です。

## 設定

| 環境変数 | 内容 |
|---|---|
| `APP_ENV` | 公開時は `production` |
| `APP_ORIGIN` | `https://example.com` の形式の正確な公開オリジン。末尾スラッシュ不要 |
| `APP_PASSWORD` | 12文字以上。ホストのSecret管理へ登録 |
| `APP_PASSWORD_HASH` | 任意。Werkzeug scryptハッシュ。設定されていればAPP_PASSWORDより優先 |
| `DATABASE_PATH` | 例 `/data/workbench.sqlite3` |
| `OPENAI_API_KEY` | 任意。サーバー側のみ。画面・Git・バックアップへ保存しない |
| `OPENAI_MODEL` | 任意。既定 `gpt-4.1-mini`。利用可能なモデルをアカウントで確認 |

本番ではSecure / HttpOnly / SameSite=Strict Cookie、8時間のサーバー保存セッションを使います。認証・CSRFを通った同一オリジンの更新だけを受け付けます。HSTSとCSP、フレーム禁止、JSON本文サイズ制限、ログイン試行制限を設定しています。プロキシのForwardedヘッダーはアプリでは信頼しません。パスワード/APIキー/受信本文をログへ出力しません。

## Docker Compose

1. `.env.example`を参照し、ホストのSecret管理または未追跡 `.env` に実際の値を設定。
2. `docker compose build` を実行。
3. `docker compose up -d` で起動。ボリューム所有者はコンテナUID 10001です。
4. HTTPSリバースプロキシから `127.0.0.1:8000` へ転送。WebSocket不要。リクエスト上限4MB程度、タイムアウト60秒以上を設定。
5. 公開HTTPSでログイン、候補登録、再起動後の保存、JSONバックアップと別環境への復元、CSV出力を実機で確認。

Composeはアプリポートをlocalhostに限定しています。インターネットから8000番へ直接アクセスさせず、HTTPS側だけを公開します。SQLite用の `workbench-data` ボリュームは削除しないでください。`docker compose down -v` はデータ削除を伴います。

## Dockerなし

LinuxのPython仮想環境に `requirements.lock` をインストールし、環境変数を設定して実行します。

```bash
gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 60 'shopee_workbench.app:create_app()'
```

systemd等でプロセスの再起動を管理し、同様にHTTPSプロキシと永続ディスクを用意します。Windowsのローカル利用は可能ですが、このGunicorn公開構成はLinux向けです。

## バックアップ・更新

- JSONの画面バックアップは商品・設定の移行向け。履歴を含む完全保存は `backup-db` コマンドを利用。
- 日次のバックアップと別の空DBでの復元訓練を実施。完全DBはセッションも含むため暗号化・アクセス制限を行う。
- 更新前にDBをバックアップ。現在のスキーマは `PRAGMA user_version=1`。未知の版なら起動を止める。
- パスワード変更時に既存セッションを失効させたい場合、停止中またはメンテナンス時間に `sessions` テーブルを空にする。
- `/api/health` は認証不要のヘルスチェック。商品や秘密情報は返さない。
- 複数人の同時共有・大量データ・複数サーバーが必要になったら、ユーザー分離とPostgreSQLへの移行を別途設計する。

## 公開後に残る確認

iPhone / Androidの実ブラウザ、バックアップの復元、ホストのディスク権限、TLS、実ショップの費用と出品テンプレート、任意AIキーでの実際の生成を確認してください。実際の自動出品・仕入れ・支払いはアプリの機能にありません。
