"""Second node: run every query on Tavily and collect the results.

This is a normal node, not a tool: the step is always the same (run all the queries),
so no LLM has to decide anything.
"""

import os

from dotenv import load_dotenv
from tavily import TavilyClient

from logs import get_logger
from schemas.search_hit import SearchHit
from state import State

load_dotenv()
log = get_logger(__name__)


def get_client() -> TavilyClient:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set. Add it to your .env file.")
    return TavilyClient(api_key=api_key)


def search_jobs(state: State) -> dict:
    """Run each query and return all the hits (duplicates are removed in a later node)."""
    search = state["settings"].search
    client = get_client()
    hits: list[SearchHit] = []
    failed = 0

    for query in state["queries"]:
        try:
            response = client.search(
                query=query,
                search_depth="basic",
                time_range=search.time_range,
                include_domains=search.domains,
                max_results=search.results_per_query,
            )
        except Exception as e:  # network error, no credits left, etc.
            log.warning("search failed for %r: %s", query, e)
            failed += 1
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

    log.info("%d queries searched -> %d results, %d searches failed",
             len(state["queries"]) - failed, len(hits), failed)
    return {"hits": hits}
