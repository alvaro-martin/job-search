"""Wires the nodes together and runs the graph.

Run from anywhere, for example from the project root:
    python src/jobagent/graph.py
"""

import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from deduplicate import deduplicate
from fetch_pages import fetch_pages
from filter_by_title import filter_by_title
from generate_queries import generate_queries
from save_jobs import save_jobs
from schemas.schemas import Dealbreakers, Preferences, Profile
from search_jobs import search_jobs
from state import State

PROFILE_PATH = Path(__file__).parent / "data" / "profile.json"


def build_graph():
    builder = StateGraph(State)
    builder.add_node("generate_queries", generate_queries)
    builder.add_node("search_jobs", search_jobs)
    builder.add_node("deduplicate", deduplicate)
    builder.add_node("filter_by_title", filter_by_title)
    builder.add_node("fetch_pages", fetch_pages)
    builder.add_node("save_jobs", save_jobs)
    builder.add_edge(START, "generate_queries")
    builder.add_edge("generate_queries", "search_jobs")
    builder.add_edge("search_jobs", "deduplicate")
    builder.add_edge("deduplicate", "filter_by_title")
    builder.add_edge("filter_by_title", "fetch_pages")
    builder.add_edge("fetch_pages", "save_jobs")
    builder.add_edge("save_jobs", END)
    return builder.compile()


def load_initial_state() -> State:
    data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return {
        "profile": Profile.model_validate(data["profile"]),
        "preferences": Preferences.model_validate(data["preferences"]),
        "dealbreakers": Dealbreakers.model_validate(data["dealbreakers"]),
        "queries": [],
        "hits": [],
        "unique_hits": [],
        "candidates": [],
        "rejected": [],
        "pages": {},
    }


if __name__ == "__main__":
    final_state = build_graph().invoke(load_initial_state())

    print("QUERIES")
    for q in final_state["queries"]:
        print(" -", q)

    print(f"\nCANDIDATES ({len(final_state['candidates'])} of {len(final_state['hits'])} hits)")
    for h in final_state["candidates"]:
        print(f" - {h.title[:70]}\n   {h.url}")

    # Peek at one fetched page, to check that the text is readable.
    if final_state["pages"]:
        url, text = next(iter(final_state["pages"].items()))
        print(f"\nSAMPLE PAGE: {url}\n{text[:800]}")
