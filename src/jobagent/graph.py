"""Wires the nodes together and runs the graph.

Run from anywhere, for example from the project root:
    python src/jobagent/graph.py
"""

from langgraph.graph import END, START, StateGraph

from deduplicate import deduplicate
from extract_jobs import extract_jobs
from fetch_pages import fetch_pages
from filter_by_title import filter_by_title
from filter_jobs import filter_jobs
from generate_queries import generate_queries
from paths import PROFILE_PATH
from save_jobs import save_jobs
from score_jobs import score_jobs
from schemas.user_profile import UserProfile
from search_jobs import search_jobs
from settings import Settings, load_settings
from state import State
from write_report import write_report


# The steps, in running order. The graph is a straight line built from this list, and the
# runner uses the order to say which step failed.
NODES = {
    "generate_queries": generate_queries,
    "search_jobs": search_jobs,
    "deduplicate": deduplicate,
    "filter_by_title": filter_by_title,
    "fetch_pages": fetch_pages,
    "extract_jobs": extract_jobs,
    "filter_jobs": filter_jobs,
    "score_jobs": score_jobs,
    "write_report": write_report,
    "save_jobs": save_jobs,
}


def build_graph():
    builder = StateGraph(State)
    for name, node in NODES.items():
        builder.add_node(name, node)
    names = list(NODES)
    builder.add_edge(START, names[0])
    for current, following in zip(names, names[1:]):
        builder.add_edge(current, following)
    builder.add_edge(names[-1], END)
    return builder.compile()


def load_initial_state(settings: Settings | None = None) -> State:
    """The starting state: the settings (loaded now unless you pass them) and your profile."""
    if settings is None:
        settings = load_settings()
    user = UserProfile.load(PROFILE_PATH)
    return {
        "settings": settings,
        "profile": user.profile,
        "preferences": user.preferences,
        "dealbreakers": user.dealbreakers,
        "queries": [],
        "hits": [],
        "unique_hits": [],
        "candidates": [],
        "rejected": [],
        "pages": {},
        "jobs": [],
        "scored_jobs": [],
        "report_path": "",
    }


if __name__ == "__main__":
    # A quick way to run everything from the terminal. It records the run in the history like
    # any other. These imports are here because runner.py imports this module.
    from logs import setup_logging
    from run_history import RunTrigger
    from runner import run_pipeline

    setup_logging()
    final_state = run_pipeline(RunTrigger.MANUAL).state

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

    print(f"\nReport: {final_state['report_path']}")
