# -*- coding: utf-8 -*-
"""
main.py — AI副業システム CLIエントリーポイント（Shopee専用）

使い方:
    python main.py shopee       # Shopee出品下書き生成
    python main.py note         # note週次レポート下書き生成
    python main.py dashboard    # dashboard.csvを更新
    python main.py all          # 上記を全部実行

※ どのコマンドも「下書き・候補の生成」までで、実際の出品・公開は行いません。
"""
import argparse

import shopee_research
import note_generator
import dashboard


def main():
    parser = argparse.ArgumentParser(description="AI副業運用システム — Shopee専用")
    parser.add_argument(
        "command",
        choices=["shopee", "note", "dashboard", "all"],
        help="実行するタスク",
    )
    parser.add_argument(
        "--target-margin", type=float, default=0.3,
        help="Shopee出品の目標利益率（デフォルト0.3=30%%）",
    )
    args = parser.parse_args()

    if args.command in ("shopee", "all"):
        shopee_research.run(target_margin=args.target_margin)

    if args.command in ("note", "all"):
        note_generator.run()

    if args.command in ("dashboard", "all"):
        dashboard.run()


if __name__ == "__main__":
    main()
