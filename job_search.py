"""
job_finder.py - v1: find the most relevant job links from the last 7 days.

Setup:
    pip install tavily-python python-dotenv
    echo "TAVILY_API_KEY=tvly-..." > .env

Run:
    python job_finder.py
"""
import os
from datetime import date
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

# ---------------------- CONFIG: edit this ----------------------
ROLES = ["AI engineer", "engenheiro de IA", "desenvolvedor Python"]
LOCATIONS = ["Brasil", "remoto"]
KEYWORDS = ["LangChain", "LangGraph", "RAG", "Python"]  # boost ranking
DOMAINS = [
    "gupy.io",
    "programathor.com.br",
    "vagas.com.br",
    "remotar.com.br",
    "trampos.co",
    "revelo.com.br",
]
TIME_RANGE = "week"  # "day" | "week" | "month" | "year"
MAX_RESULTS_PER_QUERY = 2
TOP_N = 2
# ---------------------------------------------------------------

client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


def build_queries() -> list[str]:
    return [f"vaga {role} {loc}" for role in ROLES for loc in LOCATIONS]


def normalize(url: str) -> str:
    """Strip query strings/fragments so the same job isn't listed twice."""
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))


def keyword_boost(text: str) -> float:
    text = text.lower()
    return sum(0.1 for k in KEYWORDS if k.lower() in text)


def search_all() -> list[dict]:
    found: dict[str, dict] = {}
    for query in build_queries():
        try:
            resp = client.search(
                query=query,
                time_range=TIME_RANGE,
                include_domains=DOMAINS,
                max_results=MAX_RESULTS_PER_QUERY,
                search_depth="basic",
            )
        except Exception as e:  # network, quota, etc.
            print(f"[warn] query failed: {query!r} -> {e}")
            continue

        for r in resp.get("results", []):
            key = normalize(r["url"])
            text = f"{r.get('title', '')} {r.get('content', '')}"
            score = r.get("score", 0.0) + keyword_boost(text)
            if key not in found or score > found[key]["score"]:
                found[key] = {
                    "title": r.get("title", "(no title)"),
                    "url": r["url"],
                    "snippet": r.get("content", "")[:220].replace("\n", " "),
                    "score": round(score, 3),
                    "published": r.get("published_date"),
                    "query": query,
                }
    return sorted(found.values(), key=lambda j: j["score"], reverse=True)


def save_markdown(jobs: list[dict]) -> str:
    path = f"jobs_{date.today().isoformat()}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Jobs - last 7 days ({date.today().isoformat()})\n\n")
        for i, j in enumerate(jobs, 1):
            f.write(f"{i}. [{j['title']}]({j['url']})  (score {j['score']})\n")
            f.write(f"   - {j['snippet']}\n")
            if j["published"]:
                f.write(f"   - published: {j['published']}\n")
    return path


if __name__ == "__main__":
    jobs = search_all()[:TOP_N]
    path = save_markdown(jobs)
    print(f"{len(jobs)} jobs saved to {path}")
    for j in jobs[:10]:
        print(f"- {j['title']}\n  {j['url']}")
