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

PAPER_CATEGORIES = {
    "VLA": ["vla", "vision-language-action", "vision language action",
            "language-conditioned", "rt-2", "rt-x", "openvla"],
    "World Model": ["world model", "video prediction", "latent dynamics",
                    "latent planning", "jepa", "v-jepa"],
    "Physical AI": ["physical ai", "physical intelligence", "embodied ai",
                    "embodied intelligence", "robot learning", "robot manipulation",
                    "object manipulation", "robot grasping", "locomotion", "dexterous"],
    "Foundation Model": ["foundation model", "large model", "pretrained",
                         "multi-task", "generalist agent", "generalist robot"],
}
PAPERS_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "papers_db.json")

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
- Gemini Robotics, Physical Intelligence, NVIDIA, Yann LeCun, Chelsea Finn, Sergey Levine, Moo Jin Kim, Seonghyeon Ye 관련 논문이면 특별히 강조
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

    # Update papers DB
    db = load_papers_db()
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
        f.write("- **기관**: Gemini Robotics, Physical Intelligence, NVIDIA\n")
        f.write("- **저자**: Yann LeCun, Chelsea Finn, Sergey Levine, Moo Jin Kim, Seonghyeon Ye\n\n")

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
