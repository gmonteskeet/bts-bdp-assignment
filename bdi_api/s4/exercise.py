import boto3
import requests
import polars as pl
import json
import os
import gzip
from typing import Annotated
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, status
from fastapi.params import Query

from bdi_api.settings import Settings

settings = Settings()

s4 = APIRouter(
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Something is wrong with the request"},
    },
    prefix="/api/s4",
    tags=["s4"],
)


def get_available_files(s3_client, bucket: str) -> list[str]:
    """Read the file index from S3"""
    try:
        response = s3_client.get_object(Bucket=bucket, Key="metadata/available_files.json")
        return json.loads(response["Body"].read().decode("utf-8"))
    except s3_client.exceptions.NoSuchKey:
        raise Exception("File index not found. Run the update_file_index script first.")


def download_single_file(args):
    """Download a single file and upload to S3"""
    filename, base_url, s3_bucket, s3_prefix = args
    
    url = f"{base_url}{filename}"
    s3_key = f"{s3_prefix}{filename.replace('.gz', '')}"
    
    s3 = boto3.client("s3")
    
    try:
        with requests.get(url, stream=True, timeout=10) as r:
            r.raise_for_status()
            s3.upload_fileobj(
                r.raw,
                s3_bucket,
                s3_key,
                ExtraArgs={"ContentType": "application/json"}
            )
        return (True, filename, None)
    except Exception as e:
        return (False, filename, str(e))


@s4.post("/aircraft/download")
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
    """Download files from source to S3 bucket.
    
    Uses a pre-built file index stored in S3 (metadata/available_files.json)
    to know which files exist, avoiding unnecessary 404 requests.
    """
    base_url = settings.source_url + "/2023/11/01/"
    s3_bucket = settings.s3_bucket
    s3_prefix = "raw/day=20231101/"
    
    s3 = boto3.client("s3")
    
    # Clean the S3 folder
    response = s3.list_objects_v2(Bucket=s3_bucket, Prefix=s3_prefix)
    if "Contents" in response:
        objects_to_delete = [{"Key": obj["Key"]} for obj in response["Contents"]]
        s3.delete_objects(Bucket=s3_bucket, Delete={"Objects": objects_to_delete})
    
    # Get available files from index
    available_files = get_available_files(s3, s3_bucket)
    files_to_download = available_files[:file_limit]
    
    # Prepare arguments for parallel download
    args_list = [
        (filename, base_url, s3_bucket, s3_prefix)
        for filename in files_to_download
    ]
    
    downloaded = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(download_single_file, args_list)
        
        for success, filename, error in results:
            if success:
                downloaded += 1
                print(f"Downloaded {filename} ({downloaded}/{file_limit})")
            else:
                failed += 1
                print(f"Failed {filename}: {error}")
    
    return json.dumps({
        "downloaded": downloaded,
        "failed": failed,
        "total_requested": file_limit
    })


def process_single_s3_file(args):
    """Process a single S3 file. Returns list of aircraft rows."""
    s3_bucket, s3_key = args
    
    if s3_key.endswith("/"):
        return []
    
    s3 = boto3.client("s3")
    s3_response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
    raw_bytes = s3_response["Body"].read()
    
    content = gzip.decompress(raw_bytes).decode("utf-8")
    data = json.loads(content)
    
    timestamp = data["now"]
    rows = []
    
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
        rows.append(row)
    
    return rows


@s4.post("/aircraft/prepare")
def prepare_data() -> str:
    """Obtain the data from AWS s3 and store it in the local `prepared` directory
    as done in s1.

    All the `/api/s1/aircraft/` endpoints should work as usual
    """
    s3_bucket = settings.s3_bucket
    s3_prefix = "raw/day=20231101/"
    prepared_dir = settings.prepared_dir
    
    os.makedirs(prepared_dir, exist_ok=True)
    
    # Clean prepared folder
    for file in os.listdir(prepared_dir):
        file_path = os.path.join(prepared_dir, file)
        if os.path.isfile(file_path):
            os.remove(file_path)
    
    s3 = boto3.client("s3")
    
    # List all files in S3
    response = s3.list_objects_v2(Bucket=s3_bucket, Prefix=s3_prefix)
    
    if "Contents" not in response:
        return "No files found in S3"
    
    # Prepare arguments for parallel processing
    args_list = [
        (s3_bucket, obj["Key"])
        for obj in response["Contents"]
    ]
    
    all_aircraft = []
    file_count = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = executor.map(process_single_s3_file, args_list)
        
        for rows in futures:
            if rows:
                all_aircraft.extend(rows)
                file_count += 1
    
    df = pl.DataFrame(all_aircraft, schema=settings.business_schema)
    
    output_path = os.path.join(prepared_dir, settings.parquet_name)
    df.write_parquet(output_path)
    
    return f"Prepared {len(df)} records from {file_count} files"