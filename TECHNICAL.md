# Technical Details

> Deployment, configuration, and workflow documentation for maintainers and developers.

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Workflow](#workflow)
- [Project Structure](#project-structure)
- [Common Tasks](#common-tasks)

---

## Quick Start

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
git clone https://github.com/Awesome-Image-Registration-Organization/IR-paper-update-tracker.git
cd IR-paper-update-tracker
pip install -r requirements.txt
```

### Local Run

```bash
cd src
python main.py run --env=dev
```

In `dev` mode the script will:
- Load the cache from `cached/dblp.yaml`
- Query DBLP for all configured topics
- Print logs to stdout
- **Not** write to `GITHUB_ENV`

You can inspect `aggregated_msg` and `msg` in the logs to preview the issue content.

---

## Configuration

All behavior is controlled by `config.yaml` in the project root.

```yaml
dblp:
  url: https://dblp.org/search/publ/api?q={}&format=json&h=1000
  keywords:
    - "registra"
    # ... add more keywords here
  queries:
    - "venue:IJCAI:"
    - "venue:NeurIPS:"
    # ... add more queries here
  mails:
    - "im.young@foxmail.com"
```

### Fields

| Field | Description |
|-------|-------------|
| `dblp.url` | DBLP search API endpoint. `{}` is replaced by the fully-encoded topic query. `h=1000` requests up to 1000 hits. |
| `dblp.keywords` | List of research-domain keyword groups (e.g. `registra`, `image match|feature match`). The runner iterates over all `keywords × queries` combinations, automatically URL-encoding each keyword and prepending it before calling the API. Backward-compatible with legacy single `keyword` string. |
| `dblp.queries` | List of plain-text DBLP venue restrictions. The runner automatically URL-encodes each query and prepends the encoded keyword before calling the API. |
| `dblp.secondary_keywords` | *(Optional)* Per-keyword secondary verification. For broad keyword groups, define a list of secondary keywords. Papers whose `title` + `abstract` do not contain at least one secondary keyword are discarded. |
| `dblp.mails` | The first email address (`mails[0]`) is used as the `contact_email` for the Crossref API User-Agent (`mailto:...`). Additional addresses are reserved for future mail-notification features. |

### Adding a New Venue

1. Find the DBLP venue code (e.g., `venue:ICML` or `streamid:journals/pami`).
2. Append the plain query string to `dblp.queries`. For example:
   - `venue:ICML:`
   - `streamid:journals/pami:`
3. Update `scripts/convert_cache_to_md.py` if you want the new venue to appear under a specific category in `IR-Papers.md`.
4. Update `README.md` (both English and Chinese sections) to list the new venue.

---

## Workflow

This repository uses [GitHub Actions](.github/workflows/watch.yml) to run the tracker automatically.

### Triggers

| Trigger | Description |
|---------|-------------|
| **Schedule** | Every day at 00:00 UTC+8 (`cron: 0 0 * * *`) |
| **Push** | On every push to the `main` branch |
| **Manual** | Via `workflow_dispatch` in the Actions tab |

> There is also a separate `.github/workflows/fetch-all-years.yml` workflow that can be triggered manually to collect papers from **all years** without the default 3-year window. See [Fetch Papers from All Years](#fetch-papers-from-all-years) below.

### Execution Steps

1. **Checkout** – Clones the repository.
2. **Setup Python** – Installs Python 3.10.
3. **Install Dependencies** – Runs `pip install -r requirements.txt`.
4. **Run Tracker** – Executes `src/main.py` with `--env=prod` (plus `--primary_only` for automatic runs). It assembles API queries from `keywords` + `queries`, fetches results, filters by year and secondary keywords, performs three-stage deduplication, and identifies new papers.
5. **Enrich Metadata** (inside `main.py`) – For every batch of new papers:
   - **Fetch Abstracts** – Queries Crossref → Semantic Scholar → OpenAlex → arXiv until a non-empty abstract is found.
   - **Extract Related Code** – Scans abstracts for GitHub repository URLs and stores the first match in `related_code`.
   - **Detect Tags** – Assigns keyword tags (`medi.`, `nat.`, `rs.`, `pc.`, `data.`, `dep.`, `oth.`) based on title and abstract content.
   - **Translate to Chinese** – Calls Qwen-MT-plus to translate abstracts into `abstract_cn` (skipped if `DASHSCOPE_API_KEY` is missing).
6. **Save Cache** – Writes updated papers to `cached/dblp.yaml`.
7. **Update IR-Papers.md** – Runs `scripts/convert_cache_to_md.py` to regenerate the categorized Markdown paper list from the updated cache.
8. **Setup Var** – Escapes the generated Markdown message for GitHub Actions.
9. **Push Done Work** – Commits `cached/dblp.yaml` and `IR-Papers.md` back to the `main` branch.
10. **Create Issue** – If new papers were found, opens a GitHub Issue using `.github/issue-template.md`.

### Issue Format

The issue title follows this pattern:

```
Paper Update [Venue1, Venue2, ...] @ YYYY-MM-DD
```

The issue body contains:
- A summary header for each venue with new papers (`[+N]` count)
- An unordered list of paper titles with:
  - `[PUB]` hyperlink pointing to the DBLP `ee` field
  - `[CODE]` hyperlink (if a GitHub repo URL was found in the abstract)
  - Tag badges such as **`medi.`** **`pc.`** (if automatic tag detection matched any keywords)

---

## Project Structure

```
.
├── .github/
│   ├── workflows/
│   │   ├── watch.yml              # Daily tracker workflow
│   │   └── fetch-all-years.yml    # Manual workflow to collect all years
│   └── issue-template.md          # Issue template (Nunjucks)
├── cached/
│   └── dblp.yaml                  # Persistent cache of reported papers
├── scripts/
│   ├── convert_cache_to_md.py     # Cache → IR-Papers.md
│   ├── fetch_abstracts.py         # Backfill missing abstracts
│   ├── fetch_dois.py              # Backfill missing DOIs
│   ├── fetch_related_code.py      # Extract GitHub links from abstracts
│   ├── fetch_tags.py              # Detect keyword tags
│   ├── dedup_cache_by_title.py    # Local title dedup utility
│   └── dedup_cache_global.py      # Global cross-topic dedup utility
├── src/
│   ├── main.py                    # Entry point and orchestration
│   └── utils.py                   # API calls, parsing, formatting, dedup logic
├── config.yaml                    # Venue list, keywords, and settings
├── requirements.txt               # Python dependencies
├── README.md                      # User-facing documentation
├── TECHNICAL.md                   # This file
└── AGENTS.md                      # Maintenance guide for agents
```

### Key Modules

- **`src/main.py`** – Loads cache, iterates over topics, queries DBLP, filters by year and secondary keywords, performs three-stage deduplication (`ee` → `title` → global cross-topic), compares against cache, enriches new papers (abstracts, related code, tags, Chinese translation), and writes new papers to `GITHUB_ENV`.
- **`src/utils.py`** – Contains `get_dblp_items` (JSON parsing), `deduplicate_items_by_ee` / `deduplicate_items_by_title` / global dedup logic, `filter_items_by_year` (year window filter), `get_msg` (Markdown formatting with `related_code` and `tags` support), `TAG_RULES` (automatic tag detection), and helpers for topic short-name extraction.
- **`cached/dblp.yaml`** – YAML mapping of topic → list of paper dicts with fields: `author`, `title`, `venue`, `year`, `type`, `access`, `key`, `doi`, `ee`, `url`, `abstract`, `abstract_cn`, `related_code`, `tags`. Serves as the source of truth for what has already been reported.

---

## Common Tasks

### Reset the Cache

If the cache becomes corrupted or you want to re-report all papers:

```bash
rm cached/dblp.yaml
```

The next run will treat every paper as new and recreate the cache.

### Change the Issue Schedule

Edit `.github/workflows/watch.yml`:

```yaml
schedule:
  - cron: '0 0 * * *'  # Change this cron expression
```

### Change the Message Format

Edit `src/utils.py` → `get_msg`. Keep the `aggregated` parameter behavior intact:
- `aggregated=True` → returns only the venue heading with `[+N]` count.
- `aggregated=False` → returns the heading plus the unordered paper list.

### Change the Year Window

Edit `src/utils.py` → `filter_items_by_year`:

```python
min_year = current_year - 3
max_year = current_year + 1
```

Adjust the offsets as needed.

### Fetch Papers from All Years

A dedicated workflow `.github/workflows/fetch-all-years.yml` can be triggered manually via `workflow_dispatch`. It runs `python main.py run --env=prod --all_years`, which **skips the year filter** and collects every paper returned by DBLP for the configured venues. By default it does **not** create a GitHub issue; you can opt-in via the `create_issue` input when triggering the workflow.

### Backfill Existing Papers

Several standalone scripts are provided to enrich papers already in the cache:

| Script | Purpose | Example |
|--------|---------|---------|
| `scripts/fetch_abstracts.py` | Backfill missing abstracts | `python scripts/fetch_abstracts.py --year all` |
| `scripts/fetch_dois.py` | Backfill missing DOIs | `python scripts/fetch_dois.py --year all` |
| `scripts/fetch_related_code.py` | Extract GitHub links from abstracts | `python scripts/fetch_related_code.py` |
| `scripts/fetch_tags.py` | Detect keyword tags | `python scripts/fetch_tags.py --force` |

Each script backs up `cached/dblp.yaml` to `cached/dblp.yaml.bak` before overwriting.
