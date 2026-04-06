from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import create_engine, text

from bdi_api.settings import Settings

settings = Settings()

s8 = APIRouter(
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Something is wrong with the request"},
    },
    prefix="/api/s8",
    tags=["s8"],
)


class AircraftReturn(BaseModel):
    icao: str
    registration: str | None
    type: str | None
    owner: str | None
    manufacturer: str | None
    model: str | None


class AircraftCO2Return(BaseModel):
    icao: str
    hours_flown: float
    co2: float | None


def _get_engine():
    return create_engine(settings.db_url)


@s8.get("/aircraft/")
def list_aircraft(num_results: int = 100, page: int = 0) -> list[AircraftReturn]:
    """List all aircraft with enriched data, ordered by ICAO ascending."""
    engine = _get_engine()
    offset = page * num_results

    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT icao, registration, type, owner, manufacturer, model "
                "FROM aircraft "
                "ORDER BY icao ASC "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": num_results, "offset": offset},
        )
        rows = result.mappings().all()

    engine.dispose()
    return [AircraftReturn(**row) for row in rows]


@s8.get("/aircraft/{icao}/co2")
def get_aircraft_co2(icao: str, day: str) -> AircraftCO2Return:
    """Calculate CO2 emissions for a given aircraft on a specific day.

    - Each row = 5-second observation
    - hours_flown = (num_observations * 5) / 3600
    - fuel_used_kg = hours_flown * galph * 3.04
    - co2_tons = (fuel_used_kg * 3.15) / 907.185
    """
    engine = _get_engine()

    with engine.connect() as conn:
        # Count observations for this ICAO on the given day
        count_result = conn.execute(
            text(
                "SELECT COUNT(*) as cnt, MIN(type) as type "
                "FROM observations "
                "WHERE icao = :icao AND day = :day"
            ),
            {"icao": icao, "day": day},
        )
        row = count_result.mappings().first()
        num_observations = row["cnt"]
        aircraft_type = row["type"]

        hours_flown = (num_observations * 5) / 3600

        # Look up fuel consumption rate
        co2 = None
        if aircraft_type:
            fuel_result = conn.execute(
                text("SELECT galph FROM fuel_rates WHERE type = :type"),
                {"type": aircraft_type},
            )
            fuel_row = fuel_result.mappings().first()
            if fuel_row:
                galph = fuel_row["galph"]
                fuel_used_kg = hours_flown * galph * 3.04
                co2 = (fuel_used_kg * 3.15) / 907.185

    engine.dispose()
    return AircraftCO2Return(icao=icao, hours_flown=round(hours_flown, 4), co2=round(co2, 4) if co2 is not None else None)
