"""Fourth node: throw out jobs whose TITLE already breaks a dealbreaker.

Free and instant: it runs before we pay to fetch and read the full pages.
Only rules that can be judged from a title are applied here:
  - dealbreakers.title_keywords  (e.g. "estagio", "trainee")
  - dealbreakers.stacks          (a title like "Desenvolvedor PHP" means PHP is required)
The rest of the dealbreakers need the full page and are applied in a later node.
"""

import re
import unicodedata

from schemas.search_hit import RejectedHit, SearchHit
from state import State


def normalize_text(text: str) -> str:
    """Lowercase and remove accents, so "Estágio" matches "estagio"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def contains_term(title: str, term: str) -> bool:
    """True if `term` appears in `title` as a whole word or phrase.

    Whole-word matching means "java" does NOT match "JavaScript", and
    "estagio" does NOT match "estagiario": list both spellings if you want both.
    """
    pattern = rf"(?<!\w){re.escape(normalize_text(term))}(?!\w)"
    return re.search(pattern, normalize_text(title)) is not None


def rejection_reason(hit: SearchHit, blocked: list[tuple[str, str]]) -> str | None:
    for kind, term in blocked:
        if contains_term(hit.title, term):
            return f"{kind} '{term}' in title"
    return None


def filter_by_title(state: State) -> dict:
    dealbreakers = state["dealbreakers"]
    blocked = [("title keyword", t) for t in dealbreakers.title_keywords]
    blocked += [("excluded stack", s) for s in dealbreakers.stacks]

    candidates: list[SearchHit] = []
    rejected: list[RejectedHit] = []
    for hit in state["unique_hits"]:
        reason = rejection_reason(hit, blocked)
        if reason:
            rejected.append(RejectedHit(hit=hit, reason=reason))
        else:
            candidates.append(hit)

    print(f"[title filter] {len(state['unique_hits'])} jobs -> {len(candidates)} kept, {len(rejected)} rejected")
    for r in rejected:
        print(f"   x {r.hit.title[:60]}  ({r.reason})")
    return {"candidates": candidates, "rejected": rejected}
