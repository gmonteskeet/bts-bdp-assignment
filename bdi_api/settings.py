from os.path import dirname, join

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

import bdi_api
from polars import Float64, Utf8, Int64

PROJECT_DIR = dirname(dirname(bdi_api.__file__))


class Settings(BaseSettings):
    source_url: str = Field(
        default="https://samples.adsbexchange.com/readsb-hist",
        description="Base URL to the website used to download the data.",
    )
    local_dir: str = Field(
        default=join(PROJECT_DIR, "data"),
        description="For any other value set env variable 'BDI_LOCAL_DIR'",
    )
    s3_bucket: str = Field(
        default="bdi-aircraft-gerson",
        description="Call the api like `BDI_S3_BUCKET=yourbucket uvicorn ...`",
    )
    MAX_RETRIES: int = Field(
        default=15,
        description="Maximum number of consecutive retries when downloading.",
    )
    business_columns: list = Field(
        default=["hex", "lat", "lon", "alt_baro", "gs", "track", "flight", "r", "t", "emergency"],
        description="Columns we want to keep from downloaded data.",
    )
    business_schema: dict = Field(
        default = {
            "timestamp": Float64, 
            "hex": Utf8,
            "lat": Float64,
            "lon": Float64,
            "alt_baro": Int64,
            "gs": Float64,
            "track": Float64,
            "flight": Utf8,
            "r": Utf8,
            "t": Utf8,
            "emergency": Utf8
        },
        description = "Schema for polars"
    )
    parquet_name: str = Field(
        default = "aircraft.parquet",
        description = "Assigned name for the file."
    )

    model_config = SettingsConfigDict(env_prefix="BDI_")

    @property
    def raw_dir(self) -> str:
        return join(self.local_dir, "raw")

    @property
    def prepared_dir(self) -> str:
        return join(self.local_dir, "prepared")
