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
from filter_jobs import filter_jobs
from generate_queries import generate_queries
from save_jobs import save_jobs
from score_jobs import score_jobs
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
    builder.add_node("filter_jobs", filter_jobs)
    builder.add_node("score_jobs", score_jobs)
    builder.add_node("save_jobs", save_jobs)
    builder.add_edge(START, "generate_queries")
    builder.add_edge("generate_queries", "search_jobs")
    builder.add_edge("search_jobs", "deduplicate")
    builder.add_edge("deduplicate", "filter_by_title")
    builder.add_edge("filter_by_title", "fetch_pages")
    builder.add_edge("fetch_pages", "extract_jobs")
    builder.add_edge("extract_jobs", "filter_jobs")
    builder.add_edge("filter_jobs", "score_jobs")
    builder.add_edge("score_jobs", "save_jobs")
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
        "scored_jobs": [],
    }


if __name__ == "__main__":
    final_state = build_graph().invoke(load_initial_state())

    print("QUERIES")
    for q in final_state["queries"]:
        print(" -", q)

    print(f"\nSCORED JOBS ({len(final_state['scored_jobs'])} of {len(final_state['hits'])} hits)")
    for sj in final_state["scored_jobs"]:
        job = sj.job
        work = job.work_model.value if job.work_model else "?"
        contracts = "/".join(c.value for c in job.contract_types) or "?"
        print(f" - [{sj.total_score}] {job.title} | {job.company} | {work} | {contracts}")
        print(f"   why: {sj.details.summary}")
        if job.unverified:
            print(f"   unverified: {', '.join(job.unverified)}")
        print(f"   {job.url}")

    # Save the scored jobs to a file, to review them (you can delete this)
    out_path = Path(__file__).parent / "data" / "scored_jobs.json"
    out_path.write_text(
        json.dumps(
            [sj.model_dump(mode="json") for sj in final_state["scored_jobs"]],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved to {out_path}")
