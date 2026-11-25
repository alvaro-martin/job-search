import json
from schemas.schemas import Profile, Preferences, Dealbreakers

data = json.load(open("data/example.profile.json", encoding="utf-8"))

profile = Profile.model_validate(data["profile"])
preferences = Preferences.model_validate(data["preferences"])
dealbreakers = Dealbreakers.model_validate(data["dealbreakers"])

print("OK:", preferences.target_roles)
