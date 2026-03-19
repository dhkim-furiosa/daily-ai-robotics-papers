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

import anthropic
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── Config ──────────────────────────────────────────────────────────
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "U0AH2EUF11R")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
TOP_N = 5

SEARCH_QUERIES = [
    '"vision language action" OR VLA robot',
    '"world model" robot OR manipulation OR embodied',
    '"physical AI" OR "physical intelligence" OR "embodied AI"',
]

AUTHOR_QUERIES = [
    'au:"Yann LeCun"',
    'au:"Chelsea Finn"',
    'au:"Sergey Levine"',
    'au:"Moo Jin Kim"',
    'au:"Seonghyeon Ye"',
]

PRIORITY_ORGS = [
    "google", "deepmind", "gemini", "physical intelligence",
    "nvidia", "meta", "berkeley", "stanford",
]

PRIORITY_AUTHORS = [
    "yann lecun", "chelsea finn", "sergey levine",
    "moo jin kim", "seonghyeon ye",
]

CATEGORIES = ["cs.RO", "cs.AI", "cs.CV", "cs.LG"]

# ── arXiv Search ────────────────────────────────────────────────────

ARXIV_API = "http://export.arxiv.org/api/query"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def search_arxiv(query: str, max_results: int = 20, days_back: int = 7) -> list[dict]:
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

        arxiv_id = entry.find("atom:id", ARXIV_NS).text.split("/abs/")[-1]
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
    """Collect and deduplicate papers from all queries."""
    all_papers = {}

    # Topic searches
    for q in SEARCH_QUERIES:
        print(f"  Searching: {q[:60]}...")
        results = search_arxiv(q, max_results=20)
        for p in results:
            if p["id"] not in all_papers:
                all_papers[p["id"]] = p
        time.sleep(3)  # Rate limiting

    # Author searches
    for q in AUTHOR_QUERIES:
        print(f"  Searching: {q}...")
        results = search_arxiv(q, max_results=10, days_back=14)
        for p in results:
            if p["id"] not in all_papers:
                all_papers[p["id"]] = p
        time.sleep(3)

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

━━━━━━━━━━━━━━━━━━━━
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
- Gemini Robotics, Physical Intelligence, NVIDIA, Yann LeCun, Chelsea Finn, Sergey Levine, Moo Jin Kim, Seonghyeon Ye 관련 논문이면 특별히 강조

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

    # Create directory
    dir_path = os.path.join(REPO_DIR, year_month)
    os.makedirs(dir_path, exist_ok=True)

    # Write markdown
    filepath = os.path.join(dir_path, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# 📚 AI/Robotics 논문 데일리 브리핑 - {today.isoformat()}\n\n")
        f.write(f"> 자동 생성 | VLA, World Model, Physical AI 관련 상위 {TOP_N}편\n\n")

        # Paper list table
        f.write("## 📋 논문 목록\n\n")
        f.write("| # | 제목 | 저자 | 링크 |\n")
        f.write("|---|------|------|------|\n")
        for i, p in enumerate(papers, 1):
            authors_short = ", ".join(p["authors"][:3])
            if len(p["authors"]) > 3:
                authors_short += " 외"
            f.write(f"| {i} | {p['title']} | {authors_short} | [arXiv]({p['url']}) |\n")

        f.write(f"\n## 📝 상세 요약\n\n{summary}\n")

    # Update README with latest link
    readme_path = os.path.join(REPO_DIR, "README.md")
    readme_entries = []
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            readme_entries = f.read()
    else:
        readme_entries = ""

    relative_path = f"{year_month}/{filename}"
    new_entry = f"- [{today.isoformat()}](./{relative_path})"

    if new_entry not in readme_entries:
        # Rebuild README
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("# 🤖 Daily AI/Robotics Paper Briefing\n\n")
            f.write("VLA, World Model, Physical AI 관련 논문을 매일 자동으로 검색하고 한국어로 요약합니다.\n\n")
            f.write("## 📅 주요 검색 키워드\n")
            f.write("- Vision-Language-Action (VLA)\n")
            f.write("- World Model for Robotics\n")
            f.write("- Physical AI / Embodied AI\n\n")
            f.write("## 🏢 주요 추적 기관/저자\n")
            f.write("- **기관**: Gemini Robotics, Physical Intelligence, NVIDIA\n")
            f.write("- **저자**: Yann LeCun, Chelsea Finn, Sergey Levine, Moo Jin Kim, Seonghyeon Ye\n\n")
            f.write("## 📚 브리핑 아카이브\n\n")
            # Collect existing entries
            if "브리핑 아카이브" in readme_entries:
                archive_section = readme_entries.split("브리핑 아카이브\n\n")[-1]
                existing = [l for l in archive_section.strip().split("\n") if l.startswith("- [")]
            else:
                existing = []
            if new_entry not in existing:
                existing.insert(0, new_entry)
            f.write("\n".join(existing) + "\n")

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
