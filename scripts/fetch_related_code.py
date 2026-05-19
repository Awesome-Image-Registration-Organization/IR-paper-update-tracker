#!/usr/bin/env python3
"""
为 cached/dblp.yaml 中的存量论文补充 related_code 字段。

遍历所有已有论文，若存在 abstract 但缺少 related_code，
则从 abstract 中提取 GitHub 仓库链接并保存到 related_code 字段。

用法:
    python scripts/fetch_related_code.py              # 处理所有年份
    python scripts/fetch_related_code.py --year 2025  # 仅处理指定年份
"""

import argparse
import sys
import datetime
from pathlib import Path

# 将 src 加入路径以便导入 utils
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils import fetch_related_code_for_papers
from loguru import logger
import yaml
import shutil


def load_yaml(path: Path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, indent=2, allow_unicode=True)


def run(year: str = None) -> None:
    project_root = Path(__file__).parent.parent.resolve()
    cache_path = project_root / "cached" / "dblp.yaml"
    backup_path = project_root / "cached" / "dblp.yaml.bak"

    dblp_cache = load_yaml(cache_path)
    if not dblp_cache:
        logger.error(f"Failed to load cache from {cache_path}")
        sys.exit(1)

    # 收集目标论文
    targets = []
    for topic, items in dblp_cache.items():
        for item in items:
            if year and year != "all":
                paper_year = str(item.get("year", ""))
                if paper_year != year:
                    continue
            abstract = (item.get("abstract") or "").strip()
            related_code = (item.get("related_code") or "").strip()
            if abstract and not related_code:
                targets.append(item)

    logger.info(f"Total papers to scan for related_code: {len(targets)}")
    if not targets:
        logger.info("No papers need related_code extraction. Exiting.")
        return

    fetch_related_code_for_papers(targets)

    # 写回缓存
    logger.info("Saving results...")
    if cache_path.exists():
        shutil.copy2(cache_path, backup_path)
    save_yaml(cache_path, dblp_cache)
    logger.info("Done.")


if __name__ == "__main__":
    default_year = str(datetime.datetime.now().year)
    parser = argparse.ArgumentParser(description="Fetch related_code for papers in cached/dblp.yaml")
    parser.add_argument(
        "--year",
        type=str,
        default=None,
        help=f"Year to process (default: all years, use specific year like {default_year})",
    )
    args = parser.parse_args()
    run(year=args.year)
