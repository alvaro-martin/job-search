"""Wires the nodes together and runs the graph.

Run from anywhere, for example from the project root:
    python src/jobagent/graph.py
"""

import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from deduplicate import deduplicate
from extract_jobs import extract_jobs
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
    builder.add_node("extract_jobs", extract_jobs)
    builder.add_node("save_jobs", save_jobs)
    builder.add_edge(START, "generate_queries")
    builder.add_edge("generate_queries", "search_jobs")
    builder.add_edge("search_jobs", "deduplicate")
    builder.add_edge("deduplicate", "filter_by_title")
    builder.add_edge("filter_by_title", "fetch_pages")
    builder.add_edge("fetch_pages", "extract_jobs")
    builder.add_edge("extract_jobs", "save_jobs")
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
        "jobs": [],
    }


if __name__ == "__main__":
    final_state = build_graph().invoke(load_initial_state())

    print("QUERIES")
    for q in final_state["queries"]:
        print(" -", q)

    print(f"\nJOBS ({len(final_state['jobs'])} of {len(final_state['hits'])} hits)")
    for job in final_state["jobs"]:
        work = job.work_model.value if job.work_model else "?"
        contracts = "/".join(c.value for c in job.contract_types) or "?"
        print(f" - {job.title} | {job.company} | {work} | {contracts}")
        print(f"   stack: {', '.join(job.required_stack) or '?'}")
        print(f"   {job.url}")

    # Peek at one fetched page, to check that the text is readable (you can delete this)
    if final_state["pages"]:
        url, text = next(iter(final_state["pages"].items()))
        print(f"\nSAMPLE PAGE: {url}\n{text[:800]}")

    # Show the full structured job (this can be deleted later)
    if final_state["jobs"]:
        print("\nFIRST JOB (full):")
        print(final_state["jobs"][0].model_dump_json(indent=2))
