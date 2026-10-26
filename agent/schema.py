from typing import Any, Optional
from typing import Any, Optional, Union
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


class Preferences(BaseModel):
    sea: bool = False
    warm: bool = False
    with_child_friendly: bool = False
    pets: bool = False
    hotel_stars_min: Optional[int] = None


class TravelSlots(BaseModel):
    intent: str = "search"  # inspire | search | refine | book
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
        """Не затираем уже известные слоты пустыми значениями из нового ответа."""
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

class Priority(BaseModel):
    price: float = 0.5
    time: float = 0.5

class SearchDefaults(BaseModel):
    transport: str = "plane"
    max_transfers: int = 0
    hotel_min_stars: Optional[int] = None
    free_cancellation: bool = False
    pets: bool = False
    priority: Priority = Field(default_factory=Priority)

class HotelPreferences(BaseModel):
    breakfast: bool = False
    amenities: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)

class UserProfile(BaseModel):
    schema_version: int = 1
    user_id: str = "default"
    home_city: Optional[str] = None
    search_defaults: SearchDefaults = Field(default_factory=SearchDefaults)
    hotel_preferences: HotelPreferences = Field(default_factory=HotelPreferences)
    interests: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
