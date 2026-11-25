"""Wires the nodes together and runs the graph.

Run from anywhere, for example from the project root:
    python src/jobagent/graph.py
"""

import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from deduplicate import deduplicate
from generate_queries import generate_queries
from schemas.schemas import Dealbreakers, Preferences, Profile
from search_jobs import search_jobs
from state import State

PROFILE_PATH = Path(__file__).parent / "data" / "profile.json"


def build_graph():
    builder = StateGraph(State)
    builder.add_node("generate_queries", generate_queries)
    builder.add_node("search_jobs", search_jobs)
    builder.add_node("deduplicate", deduplicate)
    builder.add_edge(START, "generate_queries")
    builder.add_edge("generate_queries", "search_jobs")
    builder.add_edge("search_jobs", "deduplicate")
    builder.add_edge("deduplicate", END)
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
    }


if __name__ == "__main__":
    final_state = build_graph().invoke(load_initial_state())

    print("QUERIES")
    for q in final_state["queries"]:
        print(" -", q)

    print(f"\nUNIQUE HITS ({len(final_state['unique_hits'])} of {len(final_state['hits'])})")
    for h in final_state["unique_hits"]:
        print(f" - {h.title[:70]}\n   {h.url}")
