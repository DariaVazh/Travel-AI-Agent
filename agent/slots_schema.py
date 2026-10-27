from datetime import date
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

class Dates(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    flexible_days: int = 0
    month: Optional[str] = None

    @field_validator("month", mode="before")
    @classmethod
    def month_to_str(cls, v):
        if v is None:
            return None
        return str(v)

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def validate_not_past(cls, v):
        if not v or not isinstance(v, str):
            return None
        try:
            parsed_date = date.fromisoformat(v)
            if parsed_date < date.today():
                return None
        except ValueError:
            pass
        return v

class Budget(BaseModel):
    amount: Optional[float] = None
    currency: str = "RUB"
    unlimited: bool = False
    per_person: bool = True

    @field_validator("amount", mode="before")
    @classmethod
    def amount_num(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, str) and v.lower() in {"unlimited", "безлимит"}:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

class Travelers(BaseModel):
    adults: int = 1
    children: int = 0
    infants: int = 0

class Transport(BaseModel):
    modes: list[str] = Field(default_factory=lambda: ["any"])
    max_hours: Optional[float] = None
    no_night_transfers: bool = False

    @field_validator("modes", mode="before")
    @classmethod
    def validate_modes(cls, v):
        if not v:
            return ["any"]
        if isinstance(v, str):
            v = [v]
        mapping = {
            "самолет": "plane", "самолёт": "plane", "самолетом": "plane", "самолётом": "plane", "рейс": "plane",
            "поезд": "train", "поездом": "train", "жд": "train", "железная дорога": "train",
            "любой": "any", "любым": "any", "любые": "any"
        }
        cleaned = []
        for item in v:
            item_str = str(item).lower().strip()
            val = mapping.get(item_str, item_str)
            if val in {"plane", "train", "any"}:
                cleaned.append(val)
            else:
                cleaned.append("any")
        return cleaned or ["any"]

class Preferences(BaseModel):
    sea: bool = False
    warm: bool = False
    with_child_friendly: bool = False
    pets: bool = False
    hotel_stars_min: Optional[int] = None

class TravelSlots(BaseModel):
    intent: str = "search"
    origin: Optional[str] = None
    destination: Optional[str] = None
    destination_flexible: bool = False
    dates: Dates = Field(default_factory=Dates)
    budget: Budget = Field(default_factory=Budget)
    travelers: Travelers = Field(default_factory=Travelers)
    transport: Transport = Field(default_factory=Transport)
    preferences: Preferences = Field(default_factory=Preferences)
    missing_fields: list[str] = Field(default_factory=list)
    clarifying_question: Optional[str] = None
    ready_to_search: bool = False

    def merge(self, other: "TravelSlots") -> "TravelSlots":
        data = self.model_dump()
        upd = other.model_dump(exclude_unset=True)

        def deep_merge(a: Any, b: Any) -> Any:
            if isinstance(a, dict) and isinstance(b, dict):
                out = dict(a)
                for k, v in b.items():
                    if v is None:
                        continue
                    if isinstance(v, (list, dict)) and not v:
                        continue
                    if k in out:
                        out[k] = deep_merge(out[k], v)
                    else:
                        out[k] = v
                return out
            return b if b not in (None, "", [], {}) else a

        merged = deep_merge(data, upd)
        return TravelSlots.model_validate(merged)

class UserProfile(BaseModel):
    schema_version: int = 1
    user_id: str = "default"
    home_city: Optional[str] = None
    interests: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)