"""Profile screen: upload a CV, add notes, let the AI draft a profile, review it, save it.

The saved file (data/profile.json) is what the whole pipeline runs on.
"""

import io
import re

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from paths import PROFILE_PATH
from profile_parser import ProfileInputError, extract_pdf_text, parse_profile
from schemas.schemas import ContractType, LanguageLevel, Seniority, WorkModel
from schemas.user_profile import ProfileDraft, UserProfile
from settings import ConfigError, load_settings

SENIORITY = [s.value for s in Seniority]
WORK_MODELS = [w.value for w in WorkModel]
CONTRACT_TYPES = [c.value for c in ContractType]
LANGUAGE_LEVELS = [level.value for level in LanguageLevel]


# ----------------------------- helpers (no Streamlit) ------------------
def parse_list(text: str) -> list[str]:
    """'Python, SQL\\nDocker' -> ['Python', 'SQL', 'Docker']"""
    return [item.strip() for item in re.split(r"[,\n]", text or "") if item.strip()]


def join_list(items: list[str]) -> str:
    return ", ".join(items)


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, float) and value != value) or (
        isinstance(value, str) and not value.strip()
    )


def rows_from_editor(df: pd.DataFrame, key_field: str) -> list[dict]:
    """Table rows -> list of dicts. Ignores empty cells and rows without `key_field`."""
    rows = []
    for record in df.to_dict("records"):
        clean = {}
        for key, value in record.items():
            if _is_blank(value):
                continue
            clean[key] = value.item() if hasattr(value, "item") else value  # numpy -> python
        if key_field in clean:
            rows.append(clean)
    return rows


def format_errors(error: ValidationError) -> list[str]:
    return [" → ".join(str(p) for p in e["loc"]) + f": {e['msg']}" for e in error.errors()]


def load_saved_draft() -> tuple[ProfileDraft, str | None]:
    """The saved profile as an editable draft (or an empty one), plus an error message if any."""
    if not PROFILE_PATH.exists():
        return ProfileDraft(), None
    try:
        user = UserProfile.load(PROFILE_PATH)
    except (ValueError, OSError) as e:
        return ProfileDraft(), f"Could not read the saved profile, starting empty: {e}"
    return ProfileDraft.model_validate(user.model_dump(mode="json")), None


# ----------------------------- screen ----------------------------------
def init_state() -> None:
    if "draft" not in st.session_state:
        draft, error = load_saved_draft()
        st.session_state.draft = draft
        st.session_state.load_error = error
        # Widget keys include this number. Bumping it recreates every widget with new values.
        st.session_state.version = 0


def analyze(uploaded, notes: str) -> None:
    try:
        model = load_settings().models.parse
        cv_text = extract_pdf_text(io.BytesIO(uploaded.getvalue())) if uploaded else ""
        with st.spinner("Reading your input with the AI..."):
            draft = parse_profile(cv_text=cv_text, notes=notes, model=model)
    except (ConfigError, ProfileInputError) as e:
        st.error(str(e))
        return
    except Exception as e:  # missing API key, network error, model error...
        st.error(f"The AI step failed: {e}\n\nCheck that the API key for your model is set in .env.")
        return
    st.session_state.draft = draft
    st.session_state.version += 1
    st.success("Draft created. Review and edit it below, then save.")


def df_languages(draft: ProfileDraft) -> pd.DataFrame:
    rows = [lang.model_dump(mode="json") for lang in draft.profile.languages]
    return pd.DataFrame(rows, columns=["name", "level"])


def df_experience(draft: ProfileDraft) -> pd.DataFrame:
    rows = [exp.model_dump(mode="json") for exp in draft.profile.experience]
    df = pd.DataFrame(rows, columns=["role", "company", "years", "description"])
    return df.astype({"years": "float64"})


def edit_form() -> None:
    draft: ProfileDraft = st.session_state.draft
    v = st.session_state.version
    key = lambda name: f"{name}_{v}"  # noqa: E731
    p, pref, d = draft.profile, draft.preferences, draft.dealbreakers
    sal = pref.salary

    with st.form("profile_form"):
        st.markdown("#### About you")
        summary = st.text_area("Summary", value=p.summary or "", key=key("summary"))
        years = st.number_input(
            "Years of experience", min_value=0.0, max_value=60.0, step=0.5,
            value=p.years_experience, key=key("years"),
        )
        skills = st.text_input("Skills (comma separated)", value=join_list(p.skills), key=key("skills"))
        st.caption("Languages")
        languages_df = st.data_editor(
            df_languages(draft), num_rows="dynamic", hide_index=True, key=key("languages"),
            column_config={
                "name": st.column_config.TextColumn("Language"),
                "level": st.column_config.SelectboxColumn("Level", options=LANGUAGE_LEVELS),
            },
        )
        st.caption("Experience")
        experience_df = st.data_editor(
            df_experience(draft), num_rows="dynamic", hide_index=True, key=key("experience"),
            column_config={
                "role": st.column_config.TextColumn("Role"),
                "company": st.column_config.TextColumn("Company"),
                "years": st.column_config.NumberColumn("Years", min_value=0, max_value=60),
                "description": st.column_config.TextColumn("Description"),
            },
        )

        st.markdown("#### What you want")
        target_roles = st.text_input(
            "Target roles (comma separated, at least one)", value=join_list(pref.target_roles),
            key=key("target_roles"),
        )
        seniority = st.multiselect("Seniority", SENIORITY, default=[s.value for s in pref.seniority], key=key("seniority"))
        work_models = st.multiselect("Work model", WORK_MODELS, default=[w.value for w in pref.work_models], key=key("work_models"))
        contract_types = st.multiselect("Contract type", CONTRACT_TYPES, default=[c.value for c in pref.contract_types], key=key("contract_types"))
        locations = st.text_input("Locations (comma separated)", value=join_list(pref.locations), key=key("locations"))
        c1, c2, c3, c4 = st.columns(4)
        sal_min = c1.number_input("Salary min", min_value=0, step=500, value=sal.min if sal else None, key=key("sal_min"))
        sal_max = c2.number_input("Salary max", min_value=0, step=500, value=sal.max if sal else None, key=key("sal_max"))
        currency = c3.text_input("Currency", value=sal.currency if sal else "BRL", max_chars=3, key=key("currency"))
        period = c4.selectbox("Per", ["month", "year"], index=0 if not sal or sal.period == "month" else 1, key=key("period"))
        keywords = st.text_input("Keywords you like to see (comma separated)", value=join_list(pref.keywords), key=key("keywords"))
        description = st.text_area("Describe your ideal job", value=pref.description or "", key=key("description"))

        st.markdown("#### What you don't want (strict: matching jobs are thrown out)")
        stacks = st.text_input("Technologies to avoid (comma separated)", value=join_list(d.stacks), key=key("stacks"))
        title_keywords = st.text_input(
            "Words that rule out a job when they are in the title",
            value=join_list(d.title_keywords), key=key("title_keywords"),
            help="Whole words, accents ignored. List variants too: estagio, estagiario, estagiaria.",
        )
        companies = st.text_input("Companies to skip (comma separated)", value=join_list(d.companies), key=key("companies"))
        d_work_models = st.multiselect("Work models to refuse", WORK_MODELS, default=[w.value for w in d.work_models], key=key("d_work_models"))
        d_contracts = st.multiselect("Contract types to refuse", CONTRACT_TYPES, default=[c.value for c in d.contract_types], key=key("d_contracts"))
        notes = st.text_area("Anything else you don't want", value=d.notes or "", key=key("d_notes"))

        saved = st.form_submit_button("Save profile", type="primary")

    if not saved:
        return

    salary = None
    if sal_min is not None or sal_max is not None:
        salary = {"min": sal_min, "max": sal_max, "currency": currency.strip().upper(), "period": period}

    data = {
        "profile": {
            "summary": summary.strip() or None,
            "years_experience": years,
            "skills": parse_list(skills),
            "languages": rows_from_editor(languages_df, "name"),
            "experience": rows_from_editor(experience_df, "role"),
        },
        "preferences": {
            "target_roles": parse_list(target_roles),
            "seniority": seniority,
            "work_models": work_models,
            "contract_types": contract_types,
            "locations": parse_list(locations),
            "salary": salary,
            "keywords": parse_list(keywords),
            "description": description.strip() or None,
        },
        "dealbreakers": {
            "stacks": parse_list(stacks),
            "title_keywords": parse_list(title_keywords),
            "companies": parse_list(companies),
            "work_models": d_work_models,
            "contract_types": d_contracts,
            "notes": notes.strip() or None,
        },
    }
    try:
        user = ProfileDraft.model_validate(data).to_user_profile()
    except ValidationError as e:
        st.error("The profile can't be saved yet:\n\n" + "\n".join(f"- {m}" for m in format_errors(e)))
        return
    user.save(PROFILE_PATH)
    st.session_state.draft = ProfileDraft.model_validate(user.model_dump(mode="json"))
    st.success(f"Profile saved to {PROFILE_PATH}")


def render() -> None:
    init_state()
    if st.session_state.load_error:
        st.warning(st.session_state.load_error)

    st.subheader("1. Tell us about you")
    st.caption(
        "Upload your CV and/or write about yourself. Phone numbers, emails and links are removed "
        "before anything is sent to the AI. Your name and address are not."
    )
    uploaded = st.file_uploader("CV (PDF with selectable text)", type="pdf")
    notes = st.text_area(
        "What you want and don't want",
        height=150,
        placeholder="Example: I want remote AI engineer jobs in Brazil, CLT. No PHP, no internships.",
    )
    if st.button("Analyze with AI", type="primary"):
        analyze(uploaded, notes)

    st.divider()
    st.subheader("2. Review and edit")
    st.caption("This replaces the form with the AI's draft when you press Analyze. Nothing is saved until you press Save.")
    edit_form()

    with st.expander("Saved profile (JSON)"):
        if PROFILE_PATH.exists():
            st.code(PROFILE_PATH.read_text(encoding="utf-8"), language="json")
        else:
            st.write("No profile saved yet.")
