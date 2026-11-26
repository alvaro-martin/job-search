"""Text matching shared by the filter nodes."""

import re
import unicodedata


def normalize_text(text: str) -> str:
    """Lowercase and remove accents, so "Estágio" matches "estagio"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def contains_term(text: str, term: str) -> bool:
    """True if `term` appears in `text` as a whole word or phrase.

    Whole-word matching means "java" does NOT match "JavaScript", and
    "estagio" does NOT match "estagiario": list both spellings if you want both.
    """
    pattern = rf"(?<!\w){re.escape(normalize_text(term))}(?!\w)"
    return re.search(pattern, normalize_text(text)) is not None
