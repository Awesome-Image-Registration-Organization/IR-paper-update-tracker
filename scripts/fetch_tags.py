#!/usr/bin/env python3
"""
批量为 cached/dblp.yaml 中的已有论文检测并附加关键词标签（tags）。

Usage:
    python scripts/fetch_tags.py              # 处理全部论文
    python scripts/fetch_tags.py --year 2025  # 仅处理指定年份
"""

import argparse
import shutil
import sys
from pathlib import Path

import yaml

# 将 src 目录加入路径以导入 utils
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from utils import detect_paper_tags_for_papers, init_log


def main():
    parser = argparse.ArgumentParser(description="Backfill paper tags for existing cache entries.")
    parser.add_argument("--year", type=str, default=None, help="Filter papers by year (e.g., 2025). Process all if omitted.")
    parser.add_argument("--force", action="store_true", help="Force re-detection even if tags already exist.")
    args = parser.parse_args()

    init_log()

    repo_root = Path(__file__).resolve().parent.parent
    cache_path = repo_root / "cached" / "dblp.yaml"
    backup_path = repo_root / "cached" / "dblp.yaml.bak"

    if not cache_path.exists():
        print(f"Cache file not found: {cache_path}")
        sys.exit(1)

    # Load cache
    with open(cache_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        print("Cache is empty.")
        sys.exit(0)

    target_papers = []
    for topic, papers in data.items():
        if not isinstance(papers, list):
            continue
        for paper in papers:
            if args.year is not None:
                if str(paper.get("year", "")) != args.year:
                    continue
            target_papers.append(paper)

    if not target_papers:
        print(f"No papers found for year={args.year}.")
        sys.exit(0)

    print(f"Processing {len(target_papers)} papers (year={args.year or 'all'})...")

    # Detect tags
    detect_paper_tags_for_papers(target_papers, force=args.force)

    # Backup original cache
    shutil.copy2(str(cache_path), str(backup_path))
    print(f"Backup created: {backup_path}")

    # Write back
    with open(cache_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, indent=2, allow_unicode=True)

    print(f"Done! Updated tags written to {cache_path}")


if __name__ == "__main__":
    main()
