from loguru import logger
from fire import Fire
from utils import (
    get_msg, init, get_dblp_items, request_data,
    deduplicate_items_by_ee, deduplicate_items_by_title,
    filter_items_by_year, get_topic_short_name,
    format_title_topics, fetch_abstract_for_papers,
    translate_abstracts_for_papers,
    filter_items_by_secondary_keywords,
    fetch_related_code_for_papers,
)
import yaml
import datetime
import urllib.parse
import os
from pathlib import Path

# 本地开发时从 .env 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass



class Scaffold:
    def __init__(self):
        pass

    def run(self, env: str = "dev", cfg: str | None = None, all_years: bool = False, primary_only: bool = False):
        cfg_path = cfg if cfg is not None else str(Path(__file__).resolve().parent.parent / "config.yaml")
        cfg = init(cfg_path=cfg_path)

        logger.info(
            f"running with env: {env}, cfg_path: {cfg_path}, all_years: {all_years}, primary_only: {primary_only}"
        )

        # dblp

        # load cache
        cache_path = cfg["cache_path"] / "dblp.yaml"
        dblp_cache = yaml.safe_load(open(cache_path, "r", encoding="utf-8")) if cache_path.exists() else {}
        # logger.info(f"dblp cache: {dblp_cache}")
        dblp_new_cache = {}

        dblp_url = cfg["dblp"]["url"]
        queries = cfg["dblp"]["queries"]
        mails = cfg["dblp"].get("mails", [])
        contact_email = mails[0] if mails else ""

        # 读取关键词列表，兼容旧版单 keyword 字符串配置
        keywords = cfg["dblp"].get("keywords", [])
        if not keywords:
            old_keyword = cfg["dblp"].get("keyword", "")
            if old_keyword:
                keywords = [old_keyword]

        # 读取二次关键词配置（ezkfg 对嵌套 dict 支持不完善，直接用 PyYAML 读取）
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                raw_cfg = yaml.safe_load(f)
            secondary_keywords_map = raw_cfg.get("dblp", {}).get("secondary_keywords", {})
        except Exception as e:
            logger.warning(
                f"Failed to load secondary_keywords from config file {cfg_path}: {e}. "
                "Proceeding with empty secondary_keywords map."
            )
            secondary_keywords_map = {}

        aggregated_msg = ""
        msg = ""
        flag = False
        active_topics = []  # 收集本次有新增论文的 topic 简称

        logger.info(f"keywords: {keywords}, queries: {queries}, primary_only: {primary_only}")

        # 全局去重集合：跨所有 topic 跟踪已见过的 ee 和 title，防止同一论文被缓存到多个 topic 下
        global_seen_ee = set()
        global_seen_title = set()
        for topic, items in dblp_cache.items():
            for item in items:
                ee = item.get("ee", "")
                title = item.get("title", "").strip()
                if ee:
                    global_seen_ee.add(ee)
                if title:
                    global_seen_title.add(title)

        def _process_topic(keyword: str, query: str) -> int:
            """处理单个 keyword + query 组合，返回新论文数量。"""
            nonlocal aggregated_msg, msg, flag
            encoded_keyword = urllib.parse.quote(keyword, safe='')
            topic = f"{encoded_keyword}%20{urllib.parse.quote(query, safe='')}"
            # random sleep to avoid being blocked
            dblp_data = request_data(dblp_url.format(topic))

            if dblp_data is None:
                logger.error(f"dblp_data is None, topic: {topic}")
                return 0

            # 解析 DBLP 返回的原始数据，提取需要的字段
            items = get_dblp_items(dblp_data)

            # 按年份过滤，仅保留近三年及未来一年的论文（如 2026 年则保留 2023-2027）
            if not all_years:
                current_year = datetime.datetime.now().year
                items = filter_items_by_year(items, current_year)

            # 二次关键词过滤：若该 keyword 配置了二次关键词，则过滤掉不匹配的结果
            sec_keywords = secondary_keywords_map.get(keyword, [])
            if sec_keywords:
                original_count = len(items)
                items = filter_items_by_secondary_keywords(items, sec_keywords)
                if len(items) < original_count:
                    logger.info(f"Secondary keyword filter for '{keyword}': {original_count} -> {len(items)}")

            # 对当前 topic 获取的论文列表先按 ee 去重，再按 title 去重
            items = deduplicate_items_by_ee(items)
            items = deduplicate_items_by_title(items)

            # 从缓存中读取该 topic 已保存的论文列表
            cached_items = dblp_cache.get(topic, [])
            # 构建已缓存论文的 ee 集合和 title 集合，用于判断哪些是新论文
            cached_ee_set = {item.get("ee", "") for item in cached_items if item.get("ee", "")}
            cached_title_set = {item.get("title", "").strip() for item in cached_items if item.get("title", "")}
            # 筛选出 ee 和 title 均不在该 topic 缓存集合中，且不在全局集合中的论文作为新论文
            new_items = [
                item for item in items
                if item.get("ee", "") not in cached_ee_set
                and item.get("title", "").strip() not in cached_title_set
                and item.get("ee", "") not in global_seen_ee
                and item.get("title", "").strip() not in global_seen_title
            ]
            dblp_new_cache[topic] = new_items

            # 将新论文的 ee 和 title 加入全局集合
            for item in new_items:
                ee = item.get("ee", "")
                title = item.get("title", "").strip()
                if ee:
                    global_seen_ee.add(ee)
                if title:
                    global_seen_title.add(title)

            # 若该 topic 首次查询，则初始化为空列表
            if topic not in dblp_cache:
                dblp_cache[topic] = []

            # 为新增论文自动获取 abstract（all_years 模式下跳过以节约运行时间）
            if new_items and not all_years:
                fetch_abstract_for_papers(new_items, sleep_sec=2.0, max_retries=4, contact_email=contact_email)
                api_key = os.getenv("DASHSCOPE_API_KEY", "")
                translate_abstracts_for_papers(new_items, api_key=api_key, sleep_sec=0.5, max_retries=3)
                fetch_related_code_for_papers(new_items)

            # 将新论文追加到缓存中（已保证无 ee/title 重复）
            dblp_cache[topic].extend(new_items)

            logger.info(f"new_items: {new_items}")

            # if there is any new items, we set flag to create a new issue
            if len(new_items) > 0:
                flag = True

            # only when new items >0 in this topic we creat the msg
            if len(new_items) > 0:
                aggregated_msg += get_msg(new_items, topic, aggregated=True)
                msg += get_msg(new_items, topic)
                # 收集该 topic 的简称，用于后续 Issue 标题
                short_name = get_topic_short_name(topic)
                if short_name not in active_topics:
                    active_topics.append(short_name)
            logger.info(f"aggregated_msg: {aggregated_msg}")
            logger.info(f"msg: {msg}")

            return len(new_items)

        if primary_only and keywords:
            # 优先级模式：先用 primary keyword 搜所有 queries，记录有新增论文的 venue
            active_queries = []
            primary_kw = keywords[0]
            for query in queries:
                n_new = _process_topic(primary_kw, query)
                if n_new > 0:
                    active_queries.append(query)
            # 再用其余 keywords 只搜有新增论文的 venue
            for keyword in keywords[1:]:
                for query in active_queries:
                    _process_topic(keyword, query)
        else:
            # 全量模式：所有 keywords × 所有 queries
            for keyword in keywords:
                for query in queries:
                    _process_topic(keyword, query)

        # save cache
        yaml.safe_dump(dblp_cache, open(cache_path, "w", encoding="utf-8"), sort_keys=False, indent=2, allow_unicode=True)

        if env == "prod":
            env_file = os.getenv("GITHUB_ENV")

            # check if msg is too long
            if len(msg) > 4096:
                msg = msg[:4096] + "..."

            if flag:
                # 生成 Issue 标题中的 topic 片段，控制长度不超过 80 字符
                title_topics = format_title_topics(active_topics)
                with open(env_file, "a") as f:
                    f.write("MSG=$'" + aggregated_msg + msg + "'\n")
                    f.write(f"ISSUE_TITLE_TOPICS={title_topics}\n")


if __name__ == "__main__":
    Fire(Scaffold)
