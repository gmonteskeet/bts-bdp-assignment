"""
Aircraft Data Pipeline DAG

Downloads ADS-B Exchange tracking data, enriches with aircraft metadata,
and loads into PostgreSQL for the API to query.

Bronze: raw JSON files in S3
Silver: cleaned + enriched Parquet in S3
Gold:   PostgreSQL tables (aircraft, observations, fuel_rates)
"""

import json
import logging
import os
from datetime import datetime

import boto3
import pandas as pd
import requests
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
S3_BUCKET = os.getenv("BDI_S3_BUCKET", "bdi-aircraft-gerson")
TRACKING_DATE = "2023/11/01"
TRACKING_DATE_DASH = "2023-11-01"
SOURCE_URL = "https://samples.adsbexchange.com/readsb-hist"
FUEL_RATES_URL = (
    "https://gist.githubusercontent.com/Jxck-S/"
    "a36314caa7dc31cd9567fc10b6f1f565/raw/"
    "aircraft_type_fuel_consumption_rate.json"
)
# Maximum number of files to DOWNLOAD (not to discover)
MAX_FILES = 200

DB_URL = os.getenv(
    "BDI_DB_URL",
    "postgresql://bdi:bdi123@localhost:5432/bdi_aircraft",
)

METADATA_KEY = f"metadata/available_files_{TRACKING_DATE_DASH}.json"

s3 = boto3.client("s3")


# ---------------------------------------------------------------------------
# Task 1: Discover ALL available JSON files and cache to S3
# ---------------------------------------------------------------------------
def discover_files(**context):
    """Scrape ADS-B Exchange to get the full list of available files for the date.

    Caches the result in S3. If cache exists and is <30 days old, skips scraping.
    This discovers ALL files — MAX_FILES is NOT applied here.
    """
    # Check if cached index exists and is fresh
    try:
        head = s3.head_object(Bucket=S3_BUCKET, Key=METADATA_KEY)
        age_days = (datetime.utcnow() - head["LastModified"].replace(tzinfo=None)).days
        if age_days < 30:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=METADATA_KEY)
            files = json.loads(obj["Body"].read())
            logger.info(f"Using cached index ({age_days} days old): {len(files)} files")
            return
    except s3.exceptions.ClientError:
        pass  # Index doesn't exist yet

    # Run Selenium scraper
    logger.info("Cache miss or stale — running Selenium discovery")
    import time

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    try:
        url = f"https://samples.adsbexchange.com/index.html#readsb-hist/{TRACKING_DATE}/"
        logger.info(f"Loading {url}")
        driver.get(url)
        time.sleep(5)

        links = driver.find_elements(By.TAG_NAME, "a")
        files = []
        for link in links:
            data_url = link.get_attribute("data-url")
            if data_url and data_url.endswith(".json.gz"):
                files.append(data_url.split("/")[-1])
        files = sorted(files)
    finally:
        driver.quit()

    # Cache ALL files to S3
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=METADATA_KEY,
        Body=json.dumps(files),
        ContentType="application/json",
    )
    logger.info(f"Cached {len(files)} files to S3")


# ---------------------------------------------------------------------------
# Task 2: Download to S3 bronze layer (parallel, limited by MAX_FILES)
# ---------------------------------------------------------------------------
def download_to_bronze(**context):
    """Download JSON files and store them in S3 bronze layer.

    Reads the full file list from S3 metadata, then downloads up to MAX_FILES.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Read file list from S3 metadata
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=METADATA_KEY)
        all_files = json.loads(obj["Body"].read())
    except Exception as e:
        logger.error(f"Cannot read metadata from S3: {e}")
        return

    files = all_files[:MAX_FILES]
    logger.info(f"Downloading {len(files)} of {len(all_files)} available files")

    bronze_prefix = f"bronze/readsb-hist/{TRACKING_DATE}"

    def download_one(filename):
        s3_key = f"{bronze_prefix}/{filename}"
        try:
            s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
            return f"SKIP {filename}"
        except s3.exceptions.ClientError:
            pass
        resp = requests.get(f"{SOURCE_URL}/{TRACKING_DATE}/{filename}", timeout=30)
        resp.raise_for_status()
        s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=resp.content)
        return f"OK {filename}"

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(download_one, f): f for f in files}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()
                logger.info(f"[{i}/{len(files)}] {result}")
            except Exception as e:
                logger.warning(f"[{i}/{len(files)}] FAIL {futures[future]}: {e}")


# ---------------------------------------------------------------------------
# Task 3: Parse bronze -> silver (clean + Parquet)
# ---------------------------------------------------------------------------
def bronze_to_silver(**context):
    """Read raw JSON from bronze, parse aircraft array, clean, save as Parquet in silver."""
    import gzip
    import io

    # Read file list from S3 metadata
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=METADATA_KEY)
        all_files = json.loads(obj["Body"].read())
    except Exception as e:
        logger.error(f"Cannot read metadata from S3: {e}")
        return

    files = all_files[:MAX_FILES]
    bronze_prefix = f"bronze/readsb-hist/{TRACKING_DATE}"
    all_records = []

    for filename in files:
        s3_key = f"{bronze_prefix}/{filename}"
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
            raw_bytes = obj["Body"].read()
            # Handle both gzipped and plain JSON
            try:
                raw = gzip.decompress(raw_bytes)
            except gzip.BadGzipFile:
                raw = raw_bytes
            data = json.loads(raw)
        except Exception as e:
            logger.warning(f"Failed to read {s3_key}: {e}")
            continue

        timestamp = data.get("now", 0)
        aircraft_list = data.get("aircraft", [])

        for ac in aircraft_list:
            hex_code = ac.get("hex", "").strip().lower()
            if not hex_code or hex_code.startswith("~"):
                continue  # Skip non-ICAO addresses

            lat = ac.get("lat")
            lon = ac.get("lon")
            if lat is None or lon is None:
                continue  # Skip aircraft without position

            record = {
                "timestamp": timestamp,
                "hex": hex_code,
                "lat": lat,
                "lon": lon,
                "alt_baro": ac.get("alt_baro") if ac.get("alt_baro") != "ground" else 0,
                "gs": ac.get("gs"),
                "track": ac.get("track"),
                "flight": (ac.get("flight") or "").strip(),
                "r": (ac.get("r") or "").strip(),
                "t": (ac.get("t") or "").strip(),
                "emergency": ac.get("emergency", "none"),
            }
            all_records.append(record)

    logger.info(f"Parsed {len(all_records)} records from {len(files)} files")

    if not all_records:
        logger.warning("No records parsed!")
        return

    df = pd.DataFrame(all_records)
    df["day"] = TRACKING_DATE_DASH

    # Save as Parquet to silver
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)

    silver_key = f"silver/aircraft/{TRACKING_DATE_DASH}/observations.parquet"
    s3.put_object(Bucket=S3_BUCKET, Key=silver_key, Body=buffer.getvalue())
    logger.info(f"Saved silver layer: {silver_key} ({len(df)} rows)")


# ---------------------------------------------------------------------------
# Task 4: Download fuel consumption rates
# ---------------------------------------------------------------------------
def download_fuel_rates(**context):
    """Download fuel consumption rates JSON and store in S3."""
    s3_key = "reference/fuel_consumption_rates.json"
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
        logger.info("Fuel rates already in S3")
        return
    except s3.exceptions.ClientError:
        pass

    resp = requests.get(FUEL_RATES_URL, timeout=30)
    resp.raise_for_status()
    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=resp.content)
    logger.info("Uploaded fuel rates to S3")


# ---------------------------------------------------------------------------
# Task 5: Load silver data into PostgreSQL
# ---------------------------------------------------------------------------
def silver_to_postgres(**context):
    """Read silver Parquet, build aircraft + observations tables in PostgreSQL."""
    import io

    silver_key = f"silver/aircraft/{TRACKING_DATE_DASH}/observations.parquet"
    obj = s3.get_object(Bucket=S3_BUCKET, Key=silver_key)
    df = pd.read_parquet(io.BytesIO(obj["Body"].read()))

    logger.info(f"Loaded {len(df)} rows from silver layer")

    engine = create_engine(DB_URL)

    # --- Aircraft table: distinct aircraft with metadata ---
    aircraft_df = (
        df.groupby("hex")
        .agg({"r": "first", "t": "first"})
        .reset_index()
        .rename(columns={"hex": "icao", "r": "registration", "t": "type"})
    )
    aircraft_df["owner"] = None
    aircraft_df["manufacturer"] = None
    aircraft_df["model"] = None

    aircraft_df.to_sql("aircraft", engine, if_exists="replace", index=False)
    logger.info(f"Loaded {len(aircraft_df)} aircraft into PostgreSQL")

    # --- Observations table: all position records ---
    obs_df = df[["hex", "lat", "lon", "alt_baro", "gs", "track", "flight", "t", "timestamp", "day"]].copy()
    obs_df = obs_df.rename(columns={"hex": "icao", "t": "type"})

    obs_df.to_sql("observations", engine, if_exists="replace", index=False)
    logger.info(f"Loaded {len(obs_df)} observations into PostgreSQL")

    # --- Fuel rates table ---
    fuel_key = "reference/fuel_consumption_rates.json"
    fuel_obj = s3.get_object(Bucket=S3_BUCKET, Key=fuel_key)
    fuel_data = json.loads(fuel_obj["Body"].read())

    fuel_records = []
    for icao_type, info in fuel_data.items():
        if isinstance(info, dict) and "galph" in info:
            fuel_records.append({"type": icao_type, "galph": info["galph"]})

    if fuel_records:
        fuel_df = pd.DataFrame(fuel_records)
        fuel_df.to_sql("fuel_rates", engine, if_exists="replace", index=False)
        logger.info(f"Loaded {len(fuel_df)} fuel rate entries into PostgreSQL")

    engine.dispose()


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
default_args = {
    "owner": "airflow",
    "retries": 1,
}

with DAG(
    dag_id="aircraft_data_pipeline",
    default_args=default_args,
    description="Download ADS-B data, process to silver, load to PostgreSQL",
    schedule=None,
    start_date=datetime(2023, 11, 1),
    catchup=False,
    tags=["bdi", "s8"],
) as dag:

    t_discover = PythonOperator(
        task_id="discover_files",
        python_callable=discover_files,
    )

    t_download = PythonOperator(
        task_id="download_to_bronze",
        python_callable=download_to_bronze,
    )

    t_silver = PythonOperator(
        task_id="bronze_to_silver",
        python_callable=bronze_to_silver,
    )

    t_fuel = PythonOperator(
        task_id="download_fuel_rates",
        python_callable=download_fuel_rates,
    )

    t_postgres = PythonOperator(
        task_id="silver_to_postgres",
        python_callable=silver_to_postgres,
    )

    t_discover >> t_download >> t_silver >> t_fuel >> t_postgres
