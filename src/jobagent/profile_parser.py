"""Turn a CV (PDF) and free-text notes into a draft profile. No UI code in here.

Steps:
  1. extract_pdf_text()      PDF -> text (pypdf; scanned PDFs are not supported)
  2. redact_contact_data()   remove emails, phones, links and ID numbers before any LLM sees the text
  3. parse_profile()         one LLM call -> ProfileDraft, which the user then reviews and edits

The redaction is best-effort: it removes what can be recognized by pattern. Your name and
street address are NOT removed, because they can't be recognized reliably.
The system prompt is a text file you can replace (JOBAGENT_PARSE_PROMPT).
"""

import os
import re
from datetime import date
from pathlib import Path
from typing import BinaryIO

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pypdf import PdfReader

from schemas.user_profile import ProfileDraft

load_dotenv()

MODEL = os.getenv("JOBAGENT_PARSE_MODEL", os.getenv("JOBAGENT_MODEL", "openai:gpt-4o-mini"))
MAX_CHARS = 30_000  # a CV is far shorter; this only guards against huge files
MIN_PDF_CHARS = 100  # less text than this means the PDF is probably a scan (images)
SYSTEM_PROMPT_PATH = Path(
    os.getenv(
        "JOBAGENT_PARSE_PROMPT", Path(__file__).parent / "prompts" / "parse_profile_system.txt"
    )
)

HUMAN_TEMPLATE = """Today's date: {today}

CV text:
{cv_text}

Candidate's notes:
{notes}"""


class ProfileInputError(ValueError):
    """The user's input can't be used. The message is written to be shown in the UI."""


# ----------------------------- 1. PDF -> text -------------------------
def extract_pdf_text(source: str | Path | BinaryIO) -> str:
    """Read the text of a PDF given a path or a file-like object (e.g. a Streamlit upload)."""
    try:
        reader = PdfReader(source)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ProfileInputError("This PDF is password-protected. Remove the password and try again.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except ProfileInputError:
        raise
    except Exception as e:
        raise ProfileInputError(f"Could not read this file as a PDF ({type(e).__name__}).") from e

    if len(text) < MIN_PDF_CHARS:
        raise ProfileInputError(
            "Almost no text was found in this PDF. It may be a scan (images). "
            "Export it as a text PDF, or paste your CV text in the notes box instead."
        )
    return text[:MAX_CHARS]


# ----------------------------- 2. remove contact data -----------------
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(
    r"(?:https?://|www\.)\S+|\b(?:linkedin|github|gitlab|behance|medium)\.com/\S*", re.IGNORECASE
)
CPF = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")  # Brazilian taxpayer id
CEP = re.compile(r"(?<!\d)\d{5}-\d{3}(?!\d)")  # Brazilian postal code
PHONE_CANDIDATE = re.compile(r"(?<![\w/])\+?\(?\d[\d ().-]{7,}\d(?![\w/])")


def _redact_phone(match: re.Match) -> str:
    raw = match.group()
    digits = len(re.sub(r"\D", "", raw))
    groups = re.findall(r"\d+", raw)
    looks_like_years = all(len(g) == 4 and g[:2] in ("19", "20") for g in groups)  # "2019 2020 2021"
    return "[phone]" if 10 <= digits <= 13 and not looks_like_years else raw


def redact_contact_data(text: str) -> str:
    text = EMAIL.sub("[email]", text)
    text = URL.sub("[link]", text)
    text = CPF.sub("[id number]", text)
    text = CEP.sub("[postal code]", text)
    return PHONE_CANDIDATE.sub(_redact_phone, text)


# ----------------------------- 3. text -> draft profile ---------------
def build_prompt() -> ChatPromptTemplate:
    # SystemMessage is not treated as a template, so the prompt file can contain any characters.
    system = SystemMessage(content=SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip())
    return ChatPromptTemplate.from_messages([system, ("human", HUMAN_TEMPLATE)])


def build_chain():
    """Prompt -> LLM -> validated ProfileDraft object."""
    llm = init_chat_model(MODEL, temperature=0)
    return build_prompt() | llm.with_structured_output(ProfileDraft)


def parse_profile(cv_text: str = "", notes: str = "") -> ProfileDraft:
    """Build a draft profile from CV text and/or the candidate's notes."""
    cv_text, notes = cv_text.strip(), notes.strip()
    if not cv_text and not notes:
        raise ProfileInputError("Upload a CV or write something about yourself first.")

    draft = build_chain().invoke(
        {
            "today": date.today().isoformat(),
            "cv_text": redact_contact_data(cv_text)[:MAX_CHARS] or "(none)",
            "notes": redact_contact_data(notes)[:MAX_CHARS] or "(none)",
        }
    )
    if draft is None:
        raise ProfileInputError("The model did not return a usable profile. Please try again.")
    return draft
