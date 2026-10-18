# Shopee Research Desk

新しいエントリーポイントは `python -m shopee_workbench serve` です。Python 3.12以上、`requirements.lock`を使います。

旧版のNodeプロキシとStreamlitは置き換えました。公開時はAPP_ENV=production、APP_ORIGIN（HTTPS）、APP_PASSWORD、永続的なDATABASE_PATHをReplit側の設定で指定し、Gunicornを使ってください。

SQLiteを保存するディスクが再起動・再デプロイで消えない構成が必要です。永続ディスクのないAutoscale構成では運用しないでください。詳しくは [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。
