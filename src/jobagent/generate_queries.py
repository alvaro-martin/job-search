"""First node of the graph: turn the user's preferences into search queries for Tavily.

Run from anywhere, for example from the project root:
    python src/jobagent/generate_queries.py
"""

import json
import os
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from logs import get_logger
from schemas.schemas import Dealbreakers, Preferences, Profile
from settings import Settings, load_settings

load_dotenv()  # reads API keys from a .env file
log = get_logger(__name__)

# The model and the number of queries are in the settings (see settings.py).
# The system prompt lives in a plain text file so anyone can replace it.
# Point JOBAGENT_QUERY_PROMPT to your own file to use a different prompt.
SYSTEM_PROMPT_PATH = Path(
    os.getenv("JOBAGENT_QUERY_PROMPT", Path(__file__).parent / "prompts" / "generate_queries_system.txt")
)
# Path relative to THIS file, so it works no matter where you run the command from
PROFILE_PATH = Path(__file__).parent / "data" / "profile.json"


# ----------------------------- state -----------------------------------
class State(TypedDict):
    """The data that travels through the graph. Each node reads and updates it."""

    settings: Settings
    profile: Profile
    preferences: Preferences
    dealbreakers: Dealbreakers
    queries: list[str]  # filled by this node


# ----------------------------- LLM output ------------------------------
class SearchQueries(BaseModel):
    """What we ask the LLM to return."""

    queries: list[str] = Field(description="Web search queries to find job postings")


# What the LLM receives as the user message. Your system prompt can rely on this:
# it always gets the max number of queries, the preferences and the dealbreakers (JSON).
HUMAN_TEMPLATE = """Return at most {max_queries} queries.

Preferences:
{preferences}

Dealbreakers (never mention these):
{dealbreakers}"""


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_prompt() -> ChatPromptTemplate:
    # SystemMessage is NOT treated as a template, so the prompt file can contain
    # any characters (including curly braces) without escaping.
    return ChatPromptTemplate.from_messages(
        [SystemMessage(content=load_system_prompt()), ("human", HUMAN_TEMPLATE)]
    )


def build_chain(model: str):
    """Prompt -> LLM -> validated SearchQueries object."""
    llm = init_chat_model(model, temperature=0.3)
    return build_prompt() | llm.with_structured_output(SearchQueries)


def clean_queries(queries: list[str], limit: int) -> list[str]:
    """Strip, drop empty and duplicate queries (ignoring case), and cap the count."""
    seen: set[str] = set()
    result: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            result.append(q)
    return result[:limit]


# ----------------------------- the node --------------------------------
def generate_queries(state: State) -> dict:
    """Read preferences + dealbreakers from the state, return the new queries."""
    settings = state["settings"]
    max_queries = settings.search.max_queries
    result = build_chain(settings.models.query).invoke(
        {
            "max_queries": max_queries,
            "preferences": state["preferences"].model_dump_json(indent=2, exclude_none=True),
            "dealbreakers": state["dealbreakers"].model_dump_json(indent=2, exclude_none=True),
        }
    )
    queries = clean_queries(result.queries, max_queries)
    log.info("%d search queries generated", len(queries))
    for query in queries:
        log.debug("query: %s", query)
    return {"queries": queries}


# ----------------------------- the graph -------------------------------
def build_graph():
    builder = StateGraph(State)
    builder.add_node("generate_queries", generate_queries)
    builder.add_edge(START, "generate_queries")
    builder.add_edge("generate_queries", END)
    return builder.compile()


if __name__ == "__main__":
    data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    initial_state = {
        "settings": load_settings(),
        "profile": Profile.model_validate(data["profile"]),
        "preferences": Preferences.model_validate(data["preferences"]),
        "dealbreakers": Dealbreakers.model_validate(data["dealbreakers"]),
        "queries": [],
    }
    final_state = build_graph().invoke(initial_state)
    for q in final_state["queries"]:
        print("-", q)
