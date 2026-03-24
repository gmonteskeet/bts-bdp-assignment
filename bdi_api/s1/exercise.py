import os
import requests
import time
import json
import polars as pl
import gzip
import glob
from typing import Annotated

from fastapi import APIRouter, status
from fastapi.params import Query

from bdi_api.settings import Settings

settings = Settings()

s1 = APIRouter(
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Something is wrong with the request"},
    },
    prefix="/api/s1",
    tags=["s1"],
)


@s1.post("/aircraft/download")
def download_data(
    file_limit: Annotated[
        int,
        Query(
            ...,
            description="""
    Limits the number of files to download.
    You must always start from the first the page returns and
    go in ascending order in order to correctly obtain the results.
    I'll test with increasing number of files starting from 100.""",
        ),
    ] = 100,
) -> str:
    """Downloads the `file_limit` files AS IS inside the folder data/20231101

    data: https://samples.adsbexchange.com/readsb-hist/2023/11/01/
    documentation: https://www.adsbexchange.com/version-2-api-wip/
        See "Trace File Fields" section

    Think about the way you organize the information inside the folder
    and the level of preprocessing you might need.

    To manipulate the data use any library you feel comfortable with.
    Just make sure to add it to `requirements.txt`
    so it can be installed using `pip install -r requirements.txt`.


    TIP: always clean the download folder before writing again to avoid having old files.
    """
    download_dir = os.path.join(settings.raw_dir, "day=20231101")
    base_url = settings.source_url + "/2023/11/01/"
    # creating the path to where the files will be stored in my local machine
    os.makedirs(download_dir, exist_ok=True)

    # cleaning the download folder
    for file in os.listdir(download_dir):
        file_path = os.path.join(download_dir, file)
        if os.path.isfile(file_path):
            os.remove(file_path)

    # making the request
    downloaded = 0
    i = 0
    retries = 0

    while downloaded < file_limit and retries < settings.MAX_RETRIES:
        seconds = i * 5
        timestamp = f"{seconds:06d}Z"

        url = f"{base_url}{timestamp}.json.gz"
        local_path = os.path.join(download_dir, f"{timestamp}.json.gz")

        try:
            # with requests.get(url, stream=True, timeout=10) as r:
            with requests.get(url, stream=True, timeout=10, headers={"Accept-Encoding": "identity"}) as r:
                # when file is not found
                if r.status_code == 404:
                    retries += 1
                    print(f"Skipped {timestamp} (404)")
                    i += 1
                    continue
                
                r.raise_for_status() # catches other errors

                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        if chunk:
                            f.write(chunk)

            downloaded += 1
            retries = 0
            print(f"Downloaded {timestamp} ({downloaded}/{file_limit})")

        except requests.RequestException:
            print(f"Skipped {timestamp}")

        i += 1
        time.sleep(0.2)
    
    if retries >= settings.MAX_RETRIES:
        print("Forced stopped because no more files were found.")

    return json.dumps({
        "downloaded": downloaded,
        "attempts": i,
        "stopped_early": retries >= settings.MAX_RETRIES
    })

@s1.post("/aircraft/prepare")
def prepare_data() -> str:
    """Prepare the data in the way you think it's better for the analysis.

    * data: https://samples.adsbexchange.com/readsb-hist/2023/11/01/
    * documentation: https://www.adsbexchange.com/version-2-api-wip/
        See "Trace File Fields" section

    Think about the way you organize the information inside the folder
    and the level of preprocessing you might need.

    To manipulate the data use any library you feel comfortable with.
    Just make sure to add it to `requirements.txt`
    so it can be installed using `pip install -r requirements.txt`.

    TIP: always clean the prepared folder before writing again to avoid having old files.

    Keep in mind that we are downloading a lot of small files, and some libraries might not work well with this!
    """
    raw_dir = os.path.join(settings.raw_dir, "day=20231101")
    prepared_dir = settings.prepared_dir
    # creating the path to where the files will be stored in my local machine
    os.makedirs(prepared_dir, exist_ok=True)
    
    # Clean prepared folder
    for file in os.listdir(prepared_dir):
        file_path = os.path.join(prepared_dir, file)
        if os.path.isfile(file_path):
            os.remove(file_path)
    
    all_aircraft = []

    for file_path in glob.glob(os.path.join(raw_dir, "*.json.gz")):
        try:
            with gzip.open(file_path, "rt") as f:
                data = json.load(f)
        except gzip.BadGzipFile:
            with open(file_path, "r") as f:
                data = json.load(f)

        timestamp = data["now"]
        
        for aircraft in data.get("aircraft", []):
            row = {"timestamp": timestamp}
            for col in settings.business_columns:
                value = aircraft.get(col)
                if col == "flight" and value is not None:
                    value = value.strip()
                if col == "emergency":
                    value = None if value == "none" else value
                if col == "alt_baro":
                    value = None if value == "ground" else value
                row[col] = value
            all_aircraft.append(row)
    
    df = pl.DataFrame(all_aircraft, schema=settings.business_schema)
    
    # Write to parquet
    output_path = os.path.join(prepared_dir, settings.parquet_name)
    df.write_parquet(output_path)
    
    return f"Prepared {len(df)} records from {len(glob.glob(os.path.join(raw_dir, '*.json.gz')))} files"


@s1.get("/aircraft/")
def list_aircraft(num_results: int = 100, page: int = 0) -> list[dict]:
    """List all the available aircraft, its registration and type ordered by
    icao asc
    """
    prepared_dir = settings.prepared_dir
    parquet_path = os.path.join(prepared_dir, settings.parquet_name)
    df = pl.read_parquet(parquet_path)
    
    # Get unique aircraft, sorted by hex (icao)
    aircraft = (
        df
        .select(["hex", "r", "t"])
        .unique(subset=["hex"])
        .sort("hex")
        .slice(page * num_results, num_results)
    )

    return [
        {"icao": row["hex"], "registration": row["r"], "type": row["t"]}
        for row in aircraft.to_dicts()
    ]


@s1.get("/aircraft/{icao}/positions")
def get_aircraft_position(icao: str, num_results: int = 1000, page: int = 0) -> list[dict]:
    """Returns all the known positions of an aircraft ordered by time (asc)
    If an aircraft is not found, return an empty list.
    """
    prepared_dir = settings.prepared_dir
    parquet_path = os.path.join(prepared_dir, settings.parquet_name)
    
    df = pl.read_parquet(parquet_path)
    
    positions = (
        df
        .filter(pl.col("hex") == icao)
        .select(["timestamp", "lat", "lon"])
        .sort("timestamp")
        .slice(page * num_results, num_results)
    )
    
    return positions.to_dicts()


@s1.get("/aircraft/{icao}/stats")
def get_aircraft_statistics(icao: str) -> dict:
    """Returns different statistics about the aircraft

    * max_altitude_baro
    * max_ground_speed
    * had_emergency
    """
    prepared_dir = settings.prepared_dir
    parquet_path = os.path.join(prepared_dir, "aircraft.parquet")
    
    df = pl.read_parquet(parquet_path)
    
    aircraft_df = df.filter(pl.col("hex") == icao)
    
    if aircraft_df.is_empty():
        return {"max_altitude_baro": None, "max_ground_speed": None, "had_emergency": False}
    
    stats = aircraft_df.select([
        pl.col("alt_baro").max().alias("max_altitude_baro"),
        pl.col("gs").max().alias("max_ground_speed"),
        pl.col("emergency").is_not_null().any().alias("had_emergency")
    ]).to_dicts()[0]
    
    return stats