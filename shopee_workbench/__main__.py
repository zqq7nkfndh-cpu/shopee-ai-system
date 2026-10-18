import argparse
import getpass
import json
import os
from .app import create_app
from .importer import load_legacy
from .store import Store


def main():
    parser = argparse.ArgumentParser(description="Shopee Research Desk")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="ローカル開発サーバーを起動")
    serve.add_argument("--port", type=int, default=8000)
    legacy = sub.add_parser(
        "import-legacy", help="旧版CSV/JSONを明示的に取り込む（既存商品は上書きしない）"
    )
    legacy.add_argument("--directory", required=True)
    legacy.add_argument(
        "--database", default=os.getenv("DATABASE_PATH", "var/workbench.sqlite3")
    )
    backup = sub.add_parser(
        "backup-db", help="オンラインDBバックアップ（履歴・セッションを含む）"
    )
    backup.add_argument("--output", required=True)
    backup.add_argument(
        "--database", default=os.getenv("DATABASE_PATH", "var/workbench.sqlite3")
    )
    args = parser.parse_args()
    if args.command == "backup-db":
        from pathlib import Path

        if not Path(args.database).is_file():
            parser.error("元のDBが見つかりません。--databaseを確認してください。")
        print(Store(args.database).backup_to(args.output))
    elif args.command == "import-legacy":
        products, warnings = load_legacy(args.directory)
        result = Store(args.database).import_candidates(products)
        print(
            json.dumps({**result, "warnings": warnings}, ensure_ascii=False, indent=2)
        )
    else:
        if not os.getenv("APP_PASSWORD") and not os.getenv("APP_PASSWORD_HASH"):
            os.environ["APP_PASSWORD"] = getpass.getpass(
                "ワークスペースのパスワード（12文字以上）: "
            )
        app = create_app()
        app.run(host="127.0.0.1", port=getattr(args, "port", 8000), debug=False)


if __name__ == "__main__":
    main()
