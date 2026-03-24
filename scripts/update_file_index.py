# scripts/update_file_index.py
import os
import json
import time
import boto3
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

SOURCE_URL = os.getenv("BDI_SOURCE_URL", "https://samples.adsbexchange.com/index.html#readsb-hist")
S3_BUCKET = os.getenv("BDI_S3_BUCKET", "bdi-aircraft-gerson")


def get_available_files():
    """Scrape the directory listing using Selenium"""
    
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    
    try:
        url = f"{SOURCE_URL}/2023/11/01/"
        print(f"Loading {url}...")
        driver.get(url)
        
        # Wait for JS to render
        time.sleep(5)
        
        links = driver.find_elements(By.TAG_NAME, "a")
        
        files = []
        for link in links:
            data_url = link.get_attribute("data-url")
            if data_url and data_url.endswith(".json.gz"):
                filename = data_url.split("/")[-1]
                files.append(filename)
        
        print(f"Found {len(files)} files")
        return sorted(files)
    
    finally:
        driver.quit()


def upload_to_s3(files):
    """Upload file index to S3"""
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=S3_BUCKET,
        Key="metadata/available_files.json",
        Body=json.dumps(files),
        ContentType="application/json"
    )
    print(f"Saved file index to s3://{S3_BUCKET}/metadata/available_files.json")


def main():
    files = get_available_files()
    upload_to_s3(files)
    print(f"Done! Indexed {len(files)} files.")


if __name__ == "__main__":
    main()