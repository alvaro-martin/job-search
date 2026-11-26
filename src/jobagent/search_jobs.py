"""Second node: run every query on Tavily and collect the results.

This is a normal node, not a tool: the step is always the same (run all the queries),
so no LLM has to decide anything.
"""

import os

from dotenv import load_dotenv
from tavily import TavilyClient

from schemas.search_hit import SearchHit
from state import State

load_dotenv()

# ---------------------- edit these ----------------------
DOMAINS = [
    "gupy.io",
    "programathor.com.br",
    "vagas.com.br",
    "remotar.com.br",
    "trampos.co",
    "revelo.com.br",
    "infojobs.com.br"
]
TIME_RANGE = "week"  # "day" | "week" | "month" | "year"
MAX_RESULTS_PER_QUERY = 1
# --------------------------------------------------------


def get_client() -> TavilyClient:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set. Add it to your .env file.")
    return TavilyClient(api_key=api_key)


def search_jobs(state: State) -> dict:
    """Run each query and return all the hits (duplicates are removed in a later node)."""
    client = get_client()
    hits: list[SearchHit] = []

    for query in state["queries"]:
        try:
            response = client.search(
                query=query,
                search_depth="basic",
                time_range=TIME_RANGE,
                include_domains=DOMAINS,
                max_results=MAX_RESULTS_PER_QUERY,
            )
        except Exception as e:  # network error, no credits left, etc.
            print(f"[warn] search failed for {query!r}: {e}")
            continue

        for r in response.get("results", []):
            hits.append(
                SearchHit(
                    url=r["url"],
                    title=r.get("title") or "",
                    snippet=r.get("content") or "",
                    score=r.get("score"),
                    published_date=r.get("published_date"),
                    query=query,
                )
            )

    return {"hits": hits}
