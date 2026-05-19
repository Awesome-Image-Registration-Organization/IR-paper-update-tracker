# Agent Guidance for IR-paper-update-tracker

> This file is intended for automated coding agents (and human maintainers) who need to understand, modify, or extend the project. Keep it up-to-date whenever architecture, logic, or conventions change.

## Project Overview

**IR-paper-update-tracker** is an automated bot that tracks new Image Registration (IR) papers published in 40+ top-tier computer-science conferences and journals. It is a satellite project of [awesome-image-registration](https://github.com/Awesome-Image-Registration-Organization/awesome-image-registration).

### High-Level Workflow
1. GitHub Actions runs the tracker once per day (cron: `0 0 * * *`) and on every push to `main`. A separate manually-triggered workflow (`.github/workflows/fetch-all-years.yml`) is also available to collect papers from **all years** without the default 3-year window.
2. `src/main.py` reads `config.yaml` → takes `dblp.keywords` (a list of search keyword groups) and `dblp.queries` (plain venue restrictions), assembles fully URL-encoded DBLP search topics, and queries the DBLP search API. In **automatic runs** (`schedule` / `push`), the `--primary_only` flag is active: only the first keyword (`registra`) is used to scan all venues; venues where `registra` discovers **new papers** are then re-scanned with the remaining keywords. This reduces API calls. **Manual runs** (`workflow_dispatch`) use all keywords for all venues.
3. Extracted paper metadata is **filtered by year** (last 3 years + next 1 year), optionally **filtered by secondary keywords** (see `config.yaml`), **deduplicated by both `ee` and `title`**, and **globally deduplicated across topics** via seen `ee`/`title` sets.
4. New papers (not yet in `cached/dblp.yaml`) are collected, formatted as Markdown, and written to the `GITHUB_ENV` variable `MSG`.
5. `scripts/convert_cache_to_md.py` regenerates `IR-Papers.md` from the updated cache.
6. If new papers exist, the action `JasonEtco/create-an-issue@v2` creates a GitHub Issue using `.github/issue-template.md`.
7. Both `cached/dblp.yaml` and `IR-Papers.md` are committed back to the repo so that subsequent runs know what has already been reported.

## Tech Stack

- **Language**: Python 3.10+
- **Core Dependencies** (see `requirements.txt`):
  - `fire` – CLI scaffolding
  - `requests` – HTTP calls to DBLP API
  - `loguru` – structured logging
  - `ezkfg` – lightweight config loader
  - `pyyaml` – cache read/write
- **CI/CD**: GitHub Actions (Ubuntu runner)
- **License**: Apache 2.0

## Directory Structure

```
.
├── .github/
│   ├── workflows/watch.yml          # GitHub Actions workflow definition
│   └── issue-template.md            # Nunjucks template for auto-created issues
├── cached/
│   └── dblp.yaml                    # Persistent cache of already-reported papers
├── scripts/
│   ├── convert_cache_to_md.py       # Converts cache to structured Markdown (domain-specific maps)
│   ├── fetch_abstracts.py           # Backfill/refresh paper abstracts via external APIs
│   ├── fetch_dois.py                # Backfill missing DOIs via DBLP / Crossref / Semantic Scholar
│   ├── dedup_cache_by_title.py      # Deduplicate cache entries by title
│   └── dedup_cache_global.py        # Global cross-topic deduplication for the cache
├── src/
│   ├── main.py                      # Entry point: assembles topics from keyword+queries, orchestrates API calls
│   └── utils.py                     # Helper functions: API call, parsing, formatting, dedup
├── config.yaml                      # keyword, plain queries (venues), and mail targets
├── IR-Papers.md                     # Structured Markdown output of all tracked papers
├── requirements.txt                 # Python dependencies
├── README.md                        # Human-facing documentation (EN + CN)
├── TECHNICAL.md                     # Deployment and configuration guide
└── AGENTS.md                        # This file
```

## Key Logic & Conventions

### 1. Year Filtering
- Location: `src/main.py` (calls `filter_items_by_year` in `src/utils.py`)
- Rule: Only papers whose `year` falls in `[current_year - 3, current_year + 1]` are kept.
- Example: In 2026, valid years are 2023–2027.
- **Agent Note**: If you change this window, update both the implementation **and** this document.

### 2. Deduplication
- Location: `src/utils.py` + `src/main.py`
- **Three-stage dedup**:
  1. `deduplicate_items_by_ee` (per-topic) — Within a single DBLP query result, papers with identical `ee` are deduplicated. Rationale: DBLP sometimes returns multiple records for the same paper with minor author-name differences (e.g., `Ming Hu 0003` vs `Ming Hu`).
  2. `deduplicate_items_by_title` (per-topic) — Within a single query result, papers with identical `title` are also deduplicated. Rationale: DBLP may list the same paper multiple times under different `ee` URLs (e.g., preprint vs. proceedings version).
  3. **Global cross-topic dedup** (in `main.py`) — A paper that has already been cached under any topic is skipped when processing subsequent topics. Rationale: DBLP search API can return the same paper for multiple venue queries (e.g., a keyword match may cross venue boundaries), so a global `seen_ee`/`seen_title` set prevents the same paper from being stored under multiple topic keys.
- **Agent Note**: Do **not** switch back to full-dict comparison (`item not in cached_items`) unless you also normalize author names.

### 3. Cache Format (`cached/dblp.yaml`)
- Top-level keys: URL-encoded DBLP search topics (e.g., `registra%20venue%3ADAC%3A:`).
- Each key maps to a list of paper dicts with fields: `author`, `title`, `venue`, `year`, `type`, `access`, `key`, `doi`, `ee`, `url`, `abstract`.
  - `abstract`  may be empty for legacy entries; use `scripts/fetch_abstracts.py` to backfill it.
- The file is overwritten after every successful run.
- **Agent Note**: If you add new fields to the paper dict, ensure backward compatibility; old cache entries missing the new field should be handled gracefully.

### 4. Message Formatting (`get_msg`)
- Location: `src/utils.py`
- `aggregated=True`: Returns only the topic heading with a `[+N]` count. Used to build the summary portion of the issue body.
- `aggregated=False`: Returns the topic heading **plus** an unordered list of papers in the form:
  ```markdown
  - {title}. [PUB]({ee})
  ```
- `get_topic_short_name` extracts the venue short name (the segment after the last `/`, or the whole name if no `/`) from a topic URL. Used for the Issue title.
- `format_title_topics` joins short names with `, ` and truncates to ≤80 characters, appending `等N个` when truncated.

### 5. Issue Title Construction
- Template: `.github/issue-template.md`
- Title: `Paper Update [{{ env.ISSUE_TITLE_TOPICS }}] @ {{ date | date('YYYY-MM-DD') }}`
- The environment variable `ISSUE_TITLE_TOPICS` is populated in `src/main.py` and passed through the workflow `env` block.

### 6. Configuration (`config.yaml`)
```yaml
dblp:
  url: https://dblp.org/search/publ/api?q={}&format=json&h=1000
  keywords:
    - "registra"
    - "image match|feature match|keypoint match|graph match|stereo match"
    - "optical flow|scene flow"
    - "stitch|panorama|mosaic"
    - "ICP"
    - "iterative closest"
    - "correspond|align"
    - "atlas construction"
    - "motion correction"
    - "deformation field"
  queries:
    - "venue:IJCAI:"
    - ...
  mails:
    - "im.young@foxmail.com"
```
- `keywords`: List of search keyword groups. Each keyword is prepended to every DBLP query. The runner iterates over all `keywords × queries` combinations. `src/main.py` is backward-compatible: if `keywords` is absent, it falls back to the legacy single `keyword` string.
- `queries`: Plain (not URL-encoded) DBLP venue restrictions; `src/main.py` combines each `keyword + query` and URL-encodes at runtime.
- `secondary_keywords`: Optional per-keyword secondary verification. For keyword groups that are overly broad (e.g., `stitch|panorama|mosaic`), you can define a list of secondary keywords. After DBLP returns results, papers whose `title` + `abstract` do not contain at least one secondary keyword are discarded. This reduces noise from unrelated domains. Example:
  ```yaml
  secondary_keywords:
    "stitch|panorama|mosaic":
      - "image"
      - "video"
      - "graph"
      - "point"
  ```
  Matching rules: `image`/`video`/`graph`/`camera` use word-boundary prefix (`\bimage` matches `image`, `images`, `imaging`…); other keywords use substring match (`point` matches `keypoint`, `viewpoint`…).
- `mails`: The first email address (`mails[0]`) is used as the `contact_email` for the Crossref API User-Agent (`mailto:...`), which is recommended for polite API access. Additional addresses are reserved for future mail-notification features.
- **Agent Note**: When adding a new venue, find its DBLP query syntax (venue code or stream ID) and append it to `dblp.queries` in plain form. When adding a new keyword group, prefer independent keywords over `|` joining multiple low-frequency two-word phrases, because DBLP can incorrectly return zero results for such combinations (see `dblp-search-keywords.md`). If the new keyword group is broad and prone to noise, consider adding a corresponding `secondary_keywords` entry.

## Maintenance Notes

### Adding a New Venue
1. Find the DBLP venue code (e.g., `venue:ICML` or `streamid:journals/pami`).
2. Append the **plain** query string to `config.yaml` under `dblp.queries` (e.g., `venue:ICML:`). The runner handles URL encoding automatically.
3. Update `scripts/convert_cache_to_md.py` if you want the new venue mapped to a specific category in `IR-Papers.md`.
4. Update `README.md` (both EN and CN sections) to list the new venue.
5. Update this `AGENTS.md` if the change affects architecture or conventions.

### Backfilling Abstracts for Existing Papers
- A standalone script `scripts/fetch_abstracts.py` is provided to backfill `abstract` fields for papers already in `cached/dblp.yaml`.
- It queries three APIs in order until a non-empty abstract is found:
  1. **Crossref** (primary) — by DOI, with `contact_email` in the User-Agent header.
  2. **Semantic Scholar** (fallback) — by DOI.
  3. **arXiv** (final fallback) — by title via `export.arxiv.org/api/query`, parsing Atom XML. arXiv enforces a minimum 3-second interval between requests.
- All queries use rate limiting, timeout handling (10s + exponential backoff), and automatic newline cleaning.
- The cache is backed up to `cached/dblp.yaml.bak` before each overwrite; `*.bak` files are ignored by git (see `.gitignore`).
- Usage:
  ```bash
  # Process current-year papers (default)
  python scripts/fetch_abstracts.py
  # Process all years
  python scripts/fetch_abstracts.py --year all
  # Retry previously failed entries (empty abstracts)
  python scripts/fetch_abstracts.py --retry-failed
  ```
- **Automatic abstract fetching**: `src/main.py` already calls `fetch_abstract_for_papers()` for every batch of new papers before saving the cache, so newly discovered papers get their abstracts filled automatically during the daily GitHub Actions run.
- **Automatic Chinese translation**: After a non-empty English `abstract` is obtained, `translate_abstracts_for_papers()` calls **Qwen-MT-plus** (via the Alibaba Cloud Bailian OpenAI-compatible API) to translate the abstract into Chinese, storing it as `abstract_cn`. Translation is skipped if the `DASHSCOPE_API_KEY` environment variable is missing, and individual translation failures do not block the pipeline.

### Backfilling DOIs for Existing Papers
- A standalone script `scripts/fetch_dois.py` is provided to backfill missing `doi` fields for papers already in `cached/dblp.yaml`.
- It queries APIs in the following priority order until a non-empty DOI is found:
  1. **DBLP API** (primary) — re-queries the paper by its `key` (e.g. `conf/dac/ChandrasekaranE22`) to check whether a DOI has been assigned since the initial fetch. This is the most authoritative source.
  2. **Crossref** (fallback) — searches by title via `api.crossref.org/works?query.title=...`.
  3. **Semantic Scholar** (final fallback) — searches by title via `api.semanticscholar.org/graph/v1/paper/search`.
- All queries use rate limiting, timeout handling (10s + exponential backoff), and title fuzzy-matching verification (`is_title_match`) to avoid assigning an incorrect DOI.
- The cache is backed up to `cached/dblp.yaml.bak` before each overwrite; `*.bak` files are ignored by git (see `.gitignore`).
- Usage:
  ```bash
  # Process current-year papers with missing DOI (default)
  python scripts/fetch_dois.py
  # Process all years
  python scripts/fetch_dois.py --year all
  # Re-fetch DOI for all papers (even those that already have one)
  python scripts/fetch_dois.py --retry-all
  ```
- A GitHub Actions workflow `.github/workflows/backfill-dois.yml` allows manual triggering from the repository UI.

### Switching to a Different Research Domain
The tracker is domain-agnostic. To pivot from Image Registration to any other field (e.g., diffusion models, LLMs, reinforcement learning):

1. **Change the keywords** in `config.yaml`:
   ```yaml
   dblp:
     keywords:
       - "diffusion"   # or LLM, "reinforcement learning", etc.
   ```
2. **Adjust the venue list** under `dblp.queries` to match the venues relevant to the new domain.
3. **Update `scripts/convert_cache_to_md.py`**:
   - `VENUE_MAP` — map DBLP raw venue names to your preferred display names.
   - `CATEGORY_MAP` — assign each display name to a category.
   - `CATEGORY_ORDER` and `VENUE_ORDER` — control the output ordering.
4. **Reset the cache** by deleting or renaming `cached/dblp.yaml` so the next run treats all fetched papers as new.
5. (Optional) Update `README.md` and `TECHNICAL.md` to reflect the new domain.

No changes to `src/main.py` or the GitHub Actions workflow are required.

### Changing Message Format
- Edit `src/utils.py` → `get_msg`.
- If you modify the Markdown structure, verify that the issue template renders correctly in GitHub.
- Keep the `aggregated` parameter behavior: `True` = heading only, `False` = heading + list.

### Changing Issue Template
- Edit `.github/issue-template.md`.
- The template engine is Nunjucks (via `JasonEtco/create-an-issue@v2`). Available variables:
  - `{{ date }}`
  - `{{ env.MSG }}`
  - `{{ env.ISSUE_TITLE_TOPICS }}`
- If you introduce a new `env` variable, also update `.github/workflows/watch.yml` to pass it through.

### Changing Workflow Schedule
- Edit `.github/workflows/watch.yml` → `schedule.cron`.
- Default is daily at 00:00 UTC+8 (`0 0 * * *`).

### Fetching Papers from All Years
- A dedicated workflow `.github/workflows/fetch-all-years.yml` can be triggered manually via `workflow_dispatch`.
- It runs `python main.py run --env=prod --all_years`, which **skips the year filter** and collects every paper returned by DBLP for the configured venues.
- By default it does **not** create a GitHub issue; you can opt-in via the `create_issue` input when triggering the workflow.

### Cache Corruption / Manual Reset
- Simply delete `cached/dblp.yaml` (or remove specific topic keys).
- The next run will treat all papers as "new" and recreate the cache.

## Testing Locally

```bash
cd src
python main.py run --env=dev

# Collect papers from all years (skip the 3-year window filter)
python main.py run --env=dev --all_years

# Simulate automatic run with primary-only mode (scans secondary keywords only on venues where registra finds new papers)
python main.py run --env=dev --primary_only
```

In `dev` mode the script will:
- Load the cache
- Query DBLP
- Print logs to stdout
- **Not** write to `GITHUB_ENV`

You can inspect `aggregated_msg` and `msg` in the logs to preview the issue content.

## Common Pitfalls

1. **Rate Limiting**: DBLP does not publish explicit rate limits. The code uses a conservative base interval (`6 + random(0.5, 2.5)` seconds for search requests) plus stricter exponential backoff with jitter and Retry-After support when requests fail or are rate-limited. Do not weaken this behavior.
2. **YAML Encoding**: `cached/dblp.yaml` is written with `allow_unicode=True`. Editing it manually with an editor that strips Unicode may corrupt author names.
3. **Empty `ee` Field**: Some older DBLP entries lack an `ee`. The deduplication logic skips empty `ee` values, so those papers are always retained. This is intentional to avoid data loss.
4. **Topic String Parsing**: `get_topic_short_name` relies on `split(":")[-2]` followed by `split("/")[-1]`. If DBLP changes its topic URL format, this will break.

## Contact & References

- Parent project: [awesome-image-registration](https://github.com/Awesome-Image-Registration-Organization/awesome-image-registration)
- Upstream inspiration: [dblp-watcher](https://github.com/beiyuouo/dblp-watcher/)
- DBLP API docs: https://dblp.org/faq/How+to+use+the+dblp+search+API.html
