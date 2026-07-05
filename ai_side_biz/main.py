# -*- coding: utf-8 -*-
"""
main.py

AI副業運用システムのCLIエントリーポイント。

使い方:
    python main.py rakuten      # 楽天ROOMリサーチ + 投稿文下書き生成
    python main.py shopee       # Shopee出品下書き生成
    python main.py note         # note週次レポート下書き生成
    python main.py dashboard    # 全体を統合したdashboard.csvを更新
    python main.py all          # 上記を順番に全部実行

※ どのコマンドも「下書き・候補の生成」までで、実際の投稿・出品・公開は行いません。
"""
import argparse

import rakuten_research
import shopee_research
import note_generator
import dashboard


def main():
    parser = argparse.ArgumentParser(description="AI副業運用システム(半自動リサーチ&下書き生成)")
    parser.add_argument(
        "command",
        choices=["rakuten", "shopee", "note", "dashboard", "all"],
        help="実行するタスク",
    )
    parser.add_argument("--genre-ids", type=str, default=None,
                         help="楽天ジャンルIDをカンマ区切りで指定(例: 100371,100804)")
    parser.add_argument("--target-margin", type=float, default=0.3,
                         help="Shopee出品の目標利益率(デフォルト0.3=30%%)")
    args = parser.parse_args()

    genre_ids = None
    if args.genre_ids:
        genre_ids = [int(g) for g in args.genre_ids.split(",")]

    if args.command in ("rakuten", "all"):
        rakuten_research.run(genre_ids=genre_ids)

    if args.command in ("shopee", "all"):
        shopee_research.run(target_margin=args.target_margin)

    if args.command in ("note", "all"):
        note_generator.run()

    if args.command in ("dashboard", "all"):
        dashboard.run()


if __name__ == "__main__":
    main()
