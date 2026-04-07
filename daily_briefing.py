#!/usr/bin/env python3
"""
Daily AI/Robotics Paper Briefing
- Searches arXiv for VLA, World Model, Physical AI papers
- Summarizes top 5 in Korean using Claude API
- Posts to Slack DM
- Commits markdown to GitHub repo
"""

import os
import sys
import json
import datetime
import subprocess
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

import re

import anthropic
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── Config ──────────────────────────────────────────────────────────
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "U0AH2EUF11R")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(REPO_DIR, "config.json")
PAPERS_DB_PATH = os.path.join(REPO_DIR, "papers_db.json")

def load_config() -> dict:
    """Load configuration from config.json."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

_config = load_config()

TOP_N = _config.get("top_n", 5)
SEARCH_QUERIES = _config["search_queries"]
AUTHOR_QUERIES = _config["author_queries"]
PRIORITY_ORGS = _config["priority_orgs"]
PRIORITY_AUTHORS = _config["priority_authors"]
CATEGORIES = _config["categories"]
PAPER_CATEGORIES = _config["paper_categories"]
AWESOME_REPOS = _config.get("awesome_repos", [])
RESEARCH_SITES = _config.get("research_sites", [])

# ── Paper DB & Categorization ──────────────────────────────────────

def md_escape(s: str) -> str:
    """Escape pipe characters for Markdown table cells."""
    return s.replace("|", "\\|")


def categorize_paper(paper: dict) -> str:
    """Classify a paper into a category based on title and abstract."""
    text = (paper["title"] + " " + paper.get("abstract", "")).lower()
    for category, keywords in PAPER_CATEGORIES.items():
        if any(kw in text for kw in keywords):
            return category
    return "Other"


def load_papers_db() -> dict:
    """Load accumulated papers DB from JSON."""
    if os.path.exists(PAPERS_DB_PATH):
        with open(PAPERS_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_papers_db(db: dict):
    """Save papers DB to JSON."""
    with open(PAPERS_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# ── arXiv Search ────────────────────────────────────────────────────

ARXIV_API = "http://export.arxiv.org/api/query"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def search_arxiv(query: str, max_results: int = 20, days_back: int = 14) -> list[dict]:
    """Search arXiv API and return papers."""
    cat_filter = " OR ".join(f"cat:{c}" for c in CATEGORIES)
    full_query = f"({query}) AND ({cat_filter})"

    params = urllib.parse.urlencode({
        "search_query": full_query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })

    url = f"{ARXIV_API}?{params}"
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)
    papers = []

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DailyBriefing/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            tree = ET.parse(resp)
    except Exception as e:
        print(f"  [WARN] arXiv query failed: {e}")
        return []

    root = tree.getroot()
    for entry in root.findall("atom:entry", ARXIV_NS):
        published_str = entry.find("atom:published", ARXIV_NS).text
        published = datetime.datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        if published < cutoff:
            continue

        arxiv_id = re.sub(r'v\d+$', '', entry.find("atom:id", ARXIV_NS).text.split("/abs/")[-1])
        title = entry.find("atom:title", ARXIV_NS).text.strip().replace("\n", " ")
        abstract = entry.find("atom:summary", ARXIV_NS).text.strip().replace("\n", " ")
        authors = [a.find("atom:name", ARXIV_NS).text for a in entry.findall("atom:author", ARXIV_NS)]
        categories = [c.get("term") for c in entry.findall("atom:category", ARXIV_NS)]

        # Extract affiliations from abstract if present
        affiliation_text = " ".join(authors).lower() + " " + abstract.lower()

        papers.append({
            "id": arxiv_id,
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "categories": categories,
            "published": published.isoformat(),
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "affiliation_text": affiliation_text,
        })

    return papers


# ── Awesome Repo Paper Fetching ────────────────────────────────────

def fetch_awesome_repo_papers(repos: list[str], days_back: int = 14) -> list[dict]:
    """Fetch recently added arxiv papers from awesome GitHub repos.

    Checks git commits within days_back to find newly added arxiv links.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    all_arxiv_ids = set()
    papers = []

    for repo in repos:
        print(f"  Checking awesome repo: {repo}...")
        try:
            # Get recent commits to find newly added papers
            commits_url = (
                f"https://api.github.com/repos/{repo}/commits"
                f"?since={cutoff_iso}&per_page=30"
            )
            req = urllib.request.Request(
                commits_url,
                headers={
                    "User-Agent": "DailyBriefing/1.0",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            github_token = os.environ.get("GITHUB_TOKEN", "")
            if github_token:
                req.add_header("Authorization", f"token {github_token}")

            with urllib.request.urlopen(req, timeout=30) as resp:
                commits = json.loads(resp.read().decode("utf-8"))

            if not commits:
                print(f"    No recent commits in {repo}")
                continue

            # Get diff for each recent commit to find added arxiv links
            for commit_info in commits[:10]:  # Check up to 10 recent commits
                sha = commit_info["sha"]
                diff_url = f"https://api.github.com/repos/{repo}/commits/{sha}"
                req = urllib.request.Request(
                    diff_url,
                    headers={
                        "User-Agent": "DailyBriefing/1.0",
                        "Accept": "application/vnd.github.v3.diff",
                    },
                )
                if github_token:
                    req.add_header("Authorization", f"token {github_token}")

                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        diff_text = resp.read().decode("utf-8", errors="replace")
                except Exception:
                    continue

                # Extract arxiv IDs from added lines (lines starting with +)
                for line in diff_text.split("\n"):
                    if not line.startswith("+"):
                        continue
                    # Match arxiv URLs in various formats
                    for match in re.finditer(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})', line):
                        arxiv_id = match.group(1)
                        if arxiv_id not in all_arxiv_ids:
                            all_arxiv_ids.add(arxiv_id)

                time.sleep(0.5)  # Rate limiting for GitHub API

        except Exception as e:
            print(f"    [WARN] Failed to fetch {repo}: {e}")
            continue

        time.sleep(1)  # Rate limiting between repos

    # Fetch paper details from arXiv for discovered IDs
    if all_arxiv_ids:
        print(f"  Found {len(all_arxiv_ids)} unique arxiv papers from awesome repos")
        papers = _fetch_arxiv_by_ids(list(all_arxiv_ids))

    return papers


def _fetch_arxiv_by_ids(arxiv_ids: list[str], batch_size: int = 20, days_back: int = 14) -> list[dict]:
    """Fetch paper metadata from arXiv API by ID list.

    Only includes papers published within days_back days.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)
    papers = []

    for i in range(0, len(arxiv_ids), batch_size):
        batch = arxiv_ids[i:i + batch_size]
        id_list = ",".join(batch)
        url = f"{ARXIV_API}?id_list={id_list}&max_results={len(batch)}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DailyBriefing/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                tree = ET.parse(resp)
        except Exception as e:
            print(f"    [WARN] arXiv batch fetch failed: {e}")
            continue

        root = tree.getroot()
        for entry in root.findall("atom:entry", ARXIV_NS):
            id_elem = entry.find("atom:id", ARXIV_NS)
            if id_elem is None:
                continue

            arxiv_id = re.sub(r'v\d+$', '', id_elem.text.split("/abs/")[-1])
            title_elem = entry.find("atom:title", ARXIV_NS)
            if title_elem is None or title_elem.text is None:
                continue

            title = title_elem.text.strip().replace("\n", " ")
            abstract = entry.find("atom:summary", ARXIV_NS).text.strip().replace("\n", " ")
            authors = [a.find("atom:name", ARXIV_NS).text for a in entry.findall("atom:author", ARXIV_NS)]
            categories = [c.get("term") for c in entry.findall("atom:category", ARXIV_NS)]
            published_str = entry.find("atom:published", ARXIV_NS).text
            published = datetime.datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            if published < cutoff:
                continue

            affiliation_text = " ".join(authors).lower() + " " + abstract.lower()

            papers.append({
                "id": arxiv_id,
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "categories": categories,
                "published": published.isoformat(),
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "affiliation_text": affiliation_text,
                "source": "awesome_repo",
            })

        time.sleep(3)  # Rate limiting

    return papers


# ── Research Site Scraping ─────────────────────────────────────────

def fetch_research_site_papers(sites: list[dict], days_back: int = 14) -> list[dict]:
    """Fetch papers from research lab websites.

    Supports two strategies:
    - 'scrape': Fetch index page, extract arxiv links (PI, DeepMind)
    - 'arxiv_search': Search arXiv with org-specific queries (NVIDIA GEAR, RLWRLD)
    """
    all_arxiv_ids = set()

    for site in sites:
        name = site["name"]
        site_type = site["type"]
        print(f"  Checking research site: {name}...")

        try:
            if site_type == "scrape":
                ids = _scrape_research_site(site, days_back)
            elif site_type == "arxiv_search":
                ids = _arxiv_search_for_org(site, days_back)
            else:
                print(f"    [WARN] Unknown site type: {site_type}")
                continue

            print(f"    Found {len(ids)} arxiv IDs from {name}")
            all_arxiv_ids.update(ids)
        except Exception as e:
            print(f"    [WARN] Failed to fetch {name}: {e}")
            continue

        time.sleep(1)

    papers = []
    if all_arxiv_ids:
        print(f"  Total {len(all_arxiv_ids)} unique arxiv papers from research sites")
        papers = _fetch_arxiv_by_ids(list(all_arxiv_ids))

    return papers


def _scrape_research_site(site: dict, days_back: int) -> set[str]:
    """Scrape a research site's index page and detail pages for arxiv IDs."""
    index_url = site["index_url"]
    base_url = site.get("base_url", "")
    filter_keywords = site.get("filter_keywords", [])
    arxiv_ids = set()

    # Fetch index page
    req = urllib.request.Request(index_url, headers={"User-Agent": "DailyBriefing/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    # Extract arxiv IDs directly from index page
    for match in re.finditer(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})', html):
        arxiv_ids.add(match.group(1))

    # If no direct arxiv links, follow detail page links
    if not arxiv_ids:
        # Extract relative links to paper detail pages
        detail_links = set()
        for match in re.finditer(r'href=["\'](/research/[^"\'#]+)["\']', html):
            link = match.group(1)
            if link == "/research/" or link == "/research":
                continue
            detail_links.add(link)

        # For DeepMind-style: extract publication links
        for match in re.finditer(r'href=["\'](?:https?://deepmind\.google)?(/research/publications/\d+/?)["\']', html):
            link = match.group(1)
            detail_links.add(link)

        # Filter by keywords if specified (check surrounding HTML context)
        if filter_keywords:
            filtered_links = set()
            for link in detail_links:
                # Find the link in HTML and check nearby text (200 chars around it)
                idx = html.find(link)
                if idx >= 0:
                    context = html[max(0, idx - 200):idx + 200].lower()
                    if any(kw in context for kw in filter_keywords):
                        filtered_links.add(link)
            detail_links = filtered_links

        # Fetch detail pages for arxiv links (limit to 15 pages)
        for link in list(detail_links)[:15]:
            full_url = base_url + link if link.startswith("/") else link
            try:
                req = urllib.request.Request(full_url, headers={"User-Agent": "DailyBriefing/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    detail_html = resp.read().decode("utf-8", errors="replace")
                for match in re.finditer(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})', detail_html):
                    arxiv_ids.add(match.group(1))
            except Exception:
                continue
            time.sleep(0.5)

    return arxiv_ids


def _arxiv_search_for_org(site: dict, days_back: int) -> set[str]:
    """Search arXiv for papers from a specific organization."""
    queries = site.get("queries", [])
    arxiv_ids = set()

    for query in queries:
        results = search_arxiv(query, max_results=15, days_back=days_back)
        for p in results:
            arxiv_ids.add(p["id"])
        time.sleep(3)

    return arxiv_ids


def score_paper(paper: dict) -> float:
    """Score paper by priority (higher = more relevant)."""
    score = 0.0
    text = paper["affiliation_text"]
    authors_lower = [a.lower() for a in paper["authors"]]

    # Priority authors
    for pa in PRIORITY_AUTHORS:
        if any(pa in a for a in authors_lower):
            score += 10.0

    # Priority orgs (check in abstract/authors text)
    for org in PRIORITY_ORGS:
        if org in text:
            score += 3.0

    # VLA / World Model / Physical AI keywords in title
    title_lower = paper["title"].lower()
    for kw in ["vla", "vision-language-action", "world model", "physical ai",
                "physical intelligence", "embodied", "foundation model"]:
        if kw in title_lower:
            score += 2.0

    return score


def collect_papers() -> list[dict]:
    """Collect and deduplicate papers from all queries, excluding previously fetched papers."""
    all_papers = {}

    # Load previously fetched papers to avoid duplicates across days
    existing_db = load_papers_db()
    # Normalize IDs by stripping version suffixes (e.g., "2603.15381v1" -> "2603.15381")
    existing_ids = set(re.sub(r'v\d+$', '', k) for k in existing_db.keys())
    skipped_count = 0

    # Topic searches
    for q in SEARCH_QUERIES:
        print(f"  Searching: {q[:60]}...")
        results = search_arxiv(q, max_results=20)
        for p in results:
            if p["id"] in existing_ids:
                skipped_count += 1
            elif p["id"] not in all_papers:
                all_papers[p["id"]] = p
        time.sleep(3)  # Rate limiting

    # Author searches
    for q in AUTHOR_QUERIES:
        print(f"  Searching: {q}...")
        results = search_arxiv(q, max_results=10, days_back=14)
        for p in results:
            if p["id"] in existing_ids:
                skipped_count += 1
            elif p["id"] not in all_papers:
                all_papers[p["id"]] = p
        time.sleep(3)

    # Awesome repo searches
    if AWESOME_REPOS:
        print(f"  Searching {len(AWESOME_REPOS)} awesome repos...")
        awesome_papers = fetch_awesome_repo_papers(AWESOME_REPOS, days_back=14)
        for p in awesome_papers:
            if p["id"] in existing_ids:
                skipped_count += 1
            elif p["id"] not in all_papers:
                all_papers[p["id"]] = p

    # Research site searches
    if RESEARCH_SITES:
        print(f"  Searching {len(RESEARCH_SITES)} research sites...")
        site_papers = fetch_research_site_papers(RESEARCH_SITES, days_back=14)
        for p in site_papers:
            if p["id"] in existing_ids:
                skipped_count += 1
            elif p["id"] not in all_papers:
                all_papers[p["id"]] = p

    if skipped_count > 0:
        print(f"  Skipped {skipped_count} previously fetched papers")

    # Score and rank
    papers = list(all_papers.values())
    for p in papers:
        p["score"] = score_paper(p)

    papers.sort(key=lambda x: x["score"], reverse=True)
    return papers[:TOP_N]


# ── Claude Summarization ───────────────────────────────────────────

def summarize_papers(papers: list[dict]) -> str:
    """Use Claude API to generate Korean summaries."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    papers_text = ""
    for i, p in enumerate(papers, 1):
        papers_text += f"""
---
Paper {i}:
Title: {p['title']}
Authors: {', '.join(p['authors'])}
URL: {p['url']}
Abstract: {p['abstract']}
---
"""

    prompt = f"""아래 {len(papers)}편의 AI/Robotics 논문을 한국어로 요약해주세요.

각 논문마다 아래 형식을 따라주세요:

📄 *N. [논문 제목 영문]*

🔗 [arXiv URL]

🏢 *기관/저자* (가능하면 소속 기관 포함)

🔬 *메소드*: 어떤 방법론을 제안했는지 핵심을 2-3문장으로 명확하게 설명

💡 *컨트리뷰션*: 기존 연구 대비 무엇이 새로운지 1-2문장

🧪 *실험*: 어떤 환경/벤치마크에서 실험했고 주요 결과는 무엇인지 구체적 수치 포함

⭐ *한줄 요약 (굵게)*

마지막에 "📌 *금주 트렌드 요약*"으로 전체 논문의 공통 트렌드를 3줄 이내로 정리해주세요.

주의사항:
- 반드시 한국어로 작성
- 메소드 설명은 기술적으로 정확하게
- Gemini Robotics, Physical Intelligence, NVIDIA GEAR, Google DeepMind, RLWRLD, World Labs, AMI, Yann LeCun, Chelsea Finn, Sergey Levine, Fei-Fei Li, Moo Jin Kim, Seonghyeon Ye, Arhan Jain, Abhishek Gupta 관련 논문이면 특별히 강조
- 논문 사이에 구분선(━, ─, — 등)을 절대 사용하지 마세요. 빈 줄로만 구분하세요

{papers_text}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text


# ── Slack Posting ──────────────────────────────────────────────────

def post_to_slack(summary: str):
    """Post summary to Slack DM."""
    client = WebClient(token=SLACK_BOT_TOKEN)
    today = datetime.date.today().isoformat()

    # Header message
    try:
        client.chat_postMessage(
            channel=SLACK_CHANNEL,
            text=f"🤖 [{today}] AI/Robotics 논문 데일리 브리핑\n\n오늘의 주요 논문 {TOP_N}편을 선별했습니다.",
        )
    except SlackApiError as e:
        print(f"  [ERROR] Slack header: {e}")

    # Split summary into chunks if too long (Slack 4000 char limit)
    chunks = []
    current = ""
    for line in summary.split("\n"):
        if len(current) + len(line) + 1 > 3800 and current:
            chunks.append(current)
            current = line
        else:
            current += "\n" + line if current else line
    if current:
        chunks.append(current)

    for chunk in chunks:
        try:
            client.chat_postMessage(channel=SLACK_CHANNEL, text=chunk)
            time.sleep(1)
        except SlackApiError as e:
            print(f"  [ERROR] Slack chunk: {e}")


# ── GitHub Commit ──────────────────────────────────────────────────

def save_and_push(summary: str, papers: list[dict]):
    """Save markdown and push to GitHub."""
    today = datetime.date.today()
    year_month = today.strftime("%Y/%m")
    filename = today.strftime("%Y-%m-%d.md")

    # Categorize papers
    for p in papers:
        p["category"] = categorize_paper(p)

    # Create directory
    dir_path = os.path.join(REPO_DIR, year_month)
    os.makedirs(dir_path, exist_ok=True)

    # Write daily markdown
    filepath = os.path.join(dir_path, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# 📚 AI/Robotics 논문 데일리 브리핑 - {today.isoformat()}\n\n")
        f.write(f"> 자동 생성 | VLA, World Model, Physical AI 관련 상위 {TOP_N}편\n\n")

        # Paper list table
        f.write("## 📋 논문 목록\n\n")
        f.write("| # | 제목 | 저자 | 카테고리 | 링크 |\n")
        f.write("|---|------|------|----------|------|\n")
        for i, p in enumerate(papers, 1):
            authors_short = ", ".join(p["authors"][:3])
            if len(p["authors"]) > 3:
                authors_short += " 외"
            f.write(f"| {i} | {md_escape(p['title'])} | {md_escape(authors_short)} | {p['category']} | [arXiv]({p['url']}) |\n")

        # Add extra blank lines between each paper summary for readability
        spaced_summary = summary.replace("\n📄", "\n\n📄")
        f.write(f"\n## 📝 상세 요약\n\n{spaced_summary}\n")

    # Update papers DB (normalize keys to strip version suffixes)
    raw_db = load_papers_db()
    db = {}
    for k, v in raw_db.items():
        normalized_key = re.sub(r'v\d+$', '', k)
        if normalized_key not in db or v["date"] < db[normalized_key]["date"]:
            db[normalized_key] = v
    for p in papers:
        db[p["id"]] = {
            "title": p["title"],
            "authors": p["authors"][:3],
            "url": p["url"],
            "category": p["category"],
            "date": today.isoformat(),
            "score": p.get("score", 0),
        }
    # Keep only last 30 days
    cutoff = (today - datetime.timedelta(days=30)).isoformat()
    db = {k: v for k, v in db.items() if v["date"] >= cutoff}
    save_papers_db(db)

    # Build README with categorized tables
    readme_path = os.path.join(REPO_DIR, "README.md")
    relative_path = f"{year_month}/{filename}"

    # Collect archive entries from existing README
    archive_entries = []
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            old_readme = f.read()
        if "브리핑 아카이브" in old_readme:
            archive_section = old_readme.split("브리핑 아카이브\n\n")[-1]
            archive_entries = [l for l in archive_section.strip().split("\n") if l.startswith("- [")]

    new_entry = f"- [{today.isoformat()}](./{relative_path})"
    if new_entry not in archive_entries:
        archive_entries.insert(0, new_entry)

    # Group papers by category
    categorized = {}
    for pid, info in sorted(db.items(), key=lambda x: x[1]["date"], reverse=True):
        cat = info["category"]
        if cat not in categorized:
            categorized[cat] = []
        categorized[cat].append(info)

    # Write README
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("# 🤖 Daily AI/Robotics Paper Briefing\n\n")
        f.write("VLA, World Model, Physical AI 관련 논문을 매일 자동으로 검색하고 한국어로 요약합니다.\n\n")
        f.write("## 📅 주요 검색 키워드\n")
        f.write("- Vision-Language-Action (VLA)\n")
        f.write("- World Model for Robotics\n")
        f.write("- Physical AI / Embodied AI\n\n")
        f.write("## 🏢 주요 추적 기관/저자\n")
        orgs_display = ", ".join(o.title() for o in PRIORITY_ORGS)
        authors_display = ", ".join(a.title() for a in PRIORITY_AUTHORS)
        f.write(f"- **기관**: {orgs_display}\n")
        f.write(f"- **저자**: {authors_display}\n\n")

        f.write("## 🔗 논문 소스\n")
        f.write("- **arXiv**: 키워드 및 저자 기반 검색\n")
        if AWESOME_REPOS:
            repos_display = ", ".join(f"[{r.split('/')[-1]}](https://github.com/{r})" for r in AWESOME_REPOS)
            f.write(f"- **Awesome Repos**: {repos_display}\n")
        if RESEARCH_SITES:
            sites_display = ", ".join(s["name"] for s in RESEARCH_SITES)
            f.write(f"- **Research Sites**: {sites_display}\n")
        f.write("\n")

        # Categorized paper tables
        f.write("## 📊 최근 논문 (카테고리별)\n\n")
        category_order = list(PAPER_CATEGORIES.keys()) + ["Other"]
        for cat in category_order:
            if cat not in categorized:
                continue
            f.write(f"### {cat}\n\n")
            f.write("| 날짜 | 제목 | 저자 | 링크 |\n")
            f.write("|------|------|------|------|\n")
            for info in categorized[cat]:
                authors_short = ", ".join(info["authors"])
                f.write(f"| {info['date']} | {md_escape(info['title'])} | {md_escape(authors_short)} | [arXiv]({info['url']}) |\n")
            f.write("\n")

        # Curated VLA study papers (from awesome-vla-study)
        f.write("## 🦾 VLA 스터디 논문 목록\n\n")
        f.write("> [awesome-vla-study](https://github.com/MilkClouds/awesome-vla-study) 기반 커리큘럼\n\n")

        f.write("### Phase 2: Early Foundation RFMs & Robot Policy\n\n")
        f.write("| # | 논문 | 링크 | 주제 |\n")
        f.write("|---|------|------|------|\n")
        f.write("| 1 | RT-1: Robotics Transformer — Brohan et al. (2022) | [2212.06817](https://arxiv.org/abs/2212.06817) | First large-scale Robotics Transformer |\n")
        f.write("| 2 | RT-2: Vision-Language-Action Models — Brohan et al. (2023) | [2307.15818](https://arxiv.org/abs/2307.15818) | VLM backbone → VLA paradigm |\n")
        f.write("| 3 | Octo — Ghosh et al. (2024) | [2405.12213](https://arxiv.org/abs/2405.12213) | Open-source generalist policy, OXE pretrained |\n")
        f.write("| 4 | OpenVLA — Kim et al. (2024) | [2406.09246](https://arxiv.org/abs/2406.09246) | First open-source VLM-based VLA |\n")
        f.write("| 5 | BeT — Shafiullah et al. (2022) | [2206.11251](https://arxiv.org/abs/2206.11251) | Multimodal action discretization |\n")
        f.write("| 6 | Diffusion Policy — Chi et al. (2023) | [2303.04137](https://arxiv.org/abs/2303.04137) | Diffusion for robot control |\n")
        f.write("| 7 | ACT/ALOHA — Zhao et al. (2023) | [2304.13705](https://arxiv.org/abs/2304.13705) | Action Chunking Transformer, bimanual |\n\n")

        f.write("### Phase 3: Current RFM Architectures\n\n")
        f.write("| # | 논문 | 링크 | 주제 |\n")
        f.write("|---|------|------|------|\n")
        f.write("| 8 | CogACT — Li et al. (2024) | [2411.19650](https://arxiv.org/abs/2411.19650) | VLM + DiT action head |\n")
        f.write("| 9 | GR00T N1 — Bjorck et al. (2025) | [2503.14734](https://arxiv.org/abs/2503.14734) | 2B diffusion transformer, humanoid |\n")
        f.write("| 10 | X-VLA — Zheng et al. (2025) | [2510.10274](https://arxiv.org/abs/2510.10274) | Cross-embodiment, flow matching |\n")
        f.write("| 11 | π0 — Black et al. (2024) | [2410.24164](https://arxiv.org/abs/2410.24164) | Flow matching + action expert |\n")
        f.write("| 12 | InternVLA-M1 — Chen et al. (2025) | [2510.13778](https://arxiv.org/abs/2510.13778) | Spatial grounding → action generation |\n\n")

        f.write("### Phase 4: Data Scaling\n\n")
        f.write("| # | 논문 | 링크 | 주제 |\n")
        f.write("|---|------|------|------|\n")
        f.write("| 13 | Open X-Embodiment (OXE) — (2023) | [2310.08864](https://arxiv.org/abs/2310.08864) | 1M+ trajectories, 22 embodiments |\n")
        f.write("| 14 | AgiBot World — Bu et al. (2025) | [2503.06669](https://arxiv.org/abs/2503.06669) | 1M+ trajectories, 217 tasks |\n")
        f.write("| 15 | UMI — Chi et al. (2024) | [2402.10329](https://arxiv.org/abs/2402.10329) | Robot-free SE(3) data collection |\n")
        f.write("| 16 | VITRA — Li et al. (2025) | [2510.21571](https://arxiv.org/abs/2510.21571) | Human video → VLA training data |\n")
        f.write("| 17 | Human to Robot Transfer — Kareer et al. (2025) | [2512.22414](https://arxiv.org/abs/2512.22414) | Human video → robot transfer |\n\n")

        f.write("### Phase 5: Efficient Inference & Dual-System\n\n")
        f.write("| # | 논문 | 링크 | 주제 |\n")
        f.write("|---|------|------|------|\n")
        f.write("| 18 | SmolVLA — Shukor et al. (2025) | [2506.01844](https://arxiv.org/abs/2506.01844) | 450M params, model compression |\n")
        f.write("| 19 | RTC — Black et al. (2025) | [2506.07339](https://arxiv.org/abs/2506.07339) | Async inference, freezing + inpainting |\n")
        f.write("| 20 | Helix — Figure AI (2025) | [figure.ai/news/helix](https://www.figure.ai/news/helix) | Dual-system humanoid |\n")
        f.write("| 21 | Fast-in-Slow — Chen et al. (2025) | [2506.01953](https://arxiv.org/abs/2506.01953) | End-to-end trainable dual-system |\n\n")

        f.write("### Phase 6: RL Fine-tuning, Reasoning & World Model\n\n")
        f.write("| # | 논문 | 링크 | 주제 |\n")
        f.write("|---|------|------|------|\n")
        f.write("| 22 | HIL-SERL — Luo et al. (2024) | [2410.21845](https://arxiv.org/abs/2410.21845) | Human-in-the-loop RL |\n")
        f.write("| 23 | SimpleVLA-RL — Li et al. (2025) | [2509.09674](https://arxiv.org/abs/2509.09674) | RL fine-tuning for AR VLA |\n")
        f.write("| 24 | π*0.6 / Recap — PI (2025) | [2511.14759](https://arxiv.org/abs/2511.14759) | RL for flow-based VLA |\n")
        f.write("| 25 | CoT-VLA — Zhao et al. (2025) | [2503.22020](https://arxiv.org/abs/2503.22020) | Visual chain-of-thought reasoning |\n")
        f.write("| 26 | ThinkAct — Huang et al. (2025) | [2507.16815](https://arxiv.org/abs/2507.16815) | Decouple reasoning from execution |\n")
        f.write("| 27 | Fast-ThinkAct — Huang et al. (2026) | [2601.09708](https://arxiv.org/abs/2601.09708) | Latent distillation, ~10x speed |\n")
        f.write("| 28 | UniVLA — Wang et al. (2025) | [2506.19850](https://arxiv.org/abs/2506.19850) | Unified AR VLA with world modeling |\n")
        f.write("| 29 | Cosmos Policy — Kim et al. (2026) | [2601.16163](https://arxiv.org/abs/2601.16163) | Video FM as robot policy backbone |\n")
        f.write("| 30 | DreamZero — Ye et al. (2026) | [dreamzero0.github.io](https://dreamzero0.github.io/) | Joint world+action generation |\n\n")

        # Archive section
        f.write("## 📚 브리핑 아카이브\n\n")
        f.write("\n".join(archive_entries) + "\n")

    # Git commit and push
    os.chdir(REPO_DIR)
    subprocess.run(["git", "add", "-A"], check=True)

    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        capture_output=True,
    )
    if result.returncode != 0:  # There are staged changes
        subprocess.run(
            ["git", "commit", "-m", f"📚 Daily briefing: {today.isoformat()}"],
            check=True,
        )
        # Try push, fall back to --set-upstream for first push
        push_result = subprocess.run(["git", "push"], capture_output=True)
        if push_result.returncode != 0:
            subprocess.run(["git", "push", "--set-upstream", "origin", "main"], check=True)
        print(f"  Pushed to GitHub: {relative_path}")
    else:
        print("  No changes to commit")


# ── Main ───────────────────────────────────────────────────────────

def main():
    today = datetime.date.today().isoformat()
    print(f"=== Daily AI/Robotics Paper Briefing ({today}) ===")

    # Validate config
    if not SLACK_BOT_TOKEN:
        print("[ERROR] SLACK_BOT_TOKEN not set")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        print("[ERROR] ANTHROPIC_API_KEY not set")
        sys.exit(1)

    # 1. Collect papers
    print("\n[1/4] Collecting papers from arXiv...")
    papers = collect_papers()
    if not papers:
        print("  No papers found. Sending notification...")
        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(
            channel=SLACK_CHANNEL,
            text=f"🤖 [{today}] AI/Robotics 논문 데일리 브리핑\n\n오늘은 관련 신규 논문이 없습니다.",
        )
        return

    print(f"  Found {len(papers)} papers")
    for i, p in enumerate(papers, 1):
        print(f"  {i}. [{p['score']:.1f}] {p['title'][:80]}")

    # 2. Summarize with Claude
    print("\n[2/4] Generating Korean summaries with Claude...")
    summary = summarize_papers(papers)
    print(f"  Summary generated ({len(summary)} chars)")

    # 3. Post to Slack
    print("\n[3/4] Posting to Slack...")
    post_to_slack(summary)
    print("  Posted to Slack")

    # 4. Save to GitHub
    print("\n[4/4] Saving to GitHub...")
    save_and_push(summary, papers)

    print(f"\n=== Done! ===")


if __name__ == "__main__":
    main()
