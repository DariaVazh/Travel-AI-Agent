from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field


class MemoryModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


MemoryText = Annotated[str, Field(min_length=1, max_length=200)]


class HotelPreferences(MemoryModel):
    min_stars: int | None = Field(default=None, ge=1, le=5)
    breakfast: bool | None = None
    near_sea: bool | None = None


class TransportPreferences(MemoryModel):
    preferred_modes: list[Literal["plane", "train"]] = Field(
        default_factory=list,
        max_length=2,
    )
    direct_only: bool | None = None
    avoid_night_travel: bool | None = None


class LongTermMemory(MemoryModel):
    schema_version: Literal[1] = 1
    home_city: MemoryText | None = None

    interests: list[MemoryText] = Field(
        default_factory=list,
        max_length=30,
    )
    dislikes: list[MemoryText] = Field(
        default_factory=list,
        max_length=30,
    )

    hotel_preferences: HotelPreferences = Field(
        default_factory=HotelPreferences,
    )
    transport_preferences: TransportPreferences = Field(
        default_factory=TransportPreferences,
    )