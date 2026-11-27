"""The whole user profile (what data/profile.json contains), and its draft form.

UserProfile     : the validated profile the pipeline runs on. Loads and saves profile.json.
ProfileDraft    : what the LLM produces from a CV and your notes. It is more lenient, because
                  the notes may not say which roles you want. You complete it in the UI and
                  then it must pass UserProfile's validation to be saved.
"""

import os
from pathlib import Path

from pydantic import Field

from schemas.schemas import Dealbreakers, Preferences, Profile, StrictModel


class UserProfile(StrictModel):
    profile: Profile = Field(default_factory=Profile)
    preferences: Preferences
    dealbreakers: Dealbreakers = Field(default_factory=Dealbreakers)

    @classmethod
    def load(cls, path: str | Path) -> "UserProfile":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def save(self, path: str | Path) -> None:
        """Write the file in one step, so a crash can never leave a half-written profile."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)


class PreferencesDraft(Preferences):
    """Same as Preferences, but target_roles may still be empty."""

    target_roles: list[str] = Field(default_factory=list)


class ProfileDraft(StrictModel):
    profile: Profile = Field(default_factory=Profile)
    preferences: PreferencesDraft = Field(default_factory=PreferencesDraft)
    dealbreakers: Dealbreakers = Field(default_factory=Dealbreakers)

    def to_user_profile(self) -> UserProfile:
        """Strict validation. Raises ValidationError if something is still missing
        (for example, no target role)."""
        return UserProfile.model_validate(self.model_dump(mode="json"))
