from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from fastapi.params import Query
from pydantic import BaseModel
from pymongo import MongoClient

from bdi_api.settings import Settings

settings = Settings()

s6 = APIRouter(
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Something is wrong with the request"},
    },
    prefix="/api/s6",
    tags=["s6"],
)


class AircraftPosition(BaseModel):
    icao: str
    registration: str | None = None
    type: str | None = None
    lat: float
    lon: float
    alt_baro: float | None = None
    ground_speed: float | None = None
    timestamp: str


def _get_collection():
    """Helper to get the MongoDB collection."""
    client = MongoClient(settings.mongo_url)
    db = client["bdi_aircraft"]
    return db["positions"]


@s6.post("/aircraft")
def create_aircraft(position: AircraftPosition) -> dict:
    """Store an aircraft position document in MongoDB."""
    collection = _get_collection()
    collection.insert_one(position.model_dump())
    return {"status": "ok"}


@s6.get("/aircraft/stats")
def aircraft_stats() -> list[dict]:
    """Return aggregated statistics: count of positions grouped by aircraft type."""
    collection = _get_collection()
    pipeline = [
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$project": {"_id": 0, "type": "$_id", "count": 1}},
    ]
    return list(collection.aggregate(pipeline))


@s6.get("/aircraft/")
def list_aircraft(
    page: Annotated[
        int,
        Query(description="Page number (1-indexed)", ge=1),
    ] = 1,
    page_size: Annotated[
        int,
        Query(description="Number of results per page", ge=1, le=100),
    ] = 20,
) -> list[dict]:
    """List all aircraft with pagination."""
    collection = _get_collection()
    skip = (page - 1) * page_size
    cursor = collection.find(
        {},
        {"_id": 0, "icao": 1, "registration": 1, "type": 1},
    ).skip(skip).limit(page_size)
    return list(cursor)


@s6.get("/aircraft/{icao}")
def get_aircraft(icao: str) -> dict:
    """Get the latest position data for a specific aircraft."""
    collection = _get_collection()
    doc = collection.find_one(
        {"icao": icao},
        {"_id": 0},
        sort=[("timestamp", -1)],
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    return doc


@s6.delete("/aircraft/{icao}")
def delete_aircraft(icao: str) -> dict:
    """Remove all position records for an aircraft."""
    collection = _get_collection()
    result = collection.delete_many({"icao": icao})
    return {"deleted": result.deleted_count}
