# tests/s4/test_exercise.py
import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from bdi_api.app import app

client = TestClient(app)


@pytest.fixture
def mock_s3():
    """Mock S3 client for all tests"""
    with patch("bdi_api.s4.exercise.boto3.client") as mock_boto:
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        mock_s3.list_objects_v2.return_value = {}
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps(["000000Z.json.gz"]).encode())
        }
        yield mock_s3


@pytest.fixture
def mock_requests():
    """Mock requests for all tests"""
    with patch("bdi_api.s4.exercise.requests.get") as mock_req:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raw = MagicMock()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_req.return_value = mock_response
        yield mock_req


class TestDownloadEndpoint:
    """Tests for POST /api/s4/aircraft/download"""
    
    def test_download_returns_success(self, mock_s3, mock_requests):
        """Test that download endpoint returns expected response structure"""
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps(["000000Z.json.gz"]).encode())
        }
        
        response = client.post("/api/s4/aircraft/download?file_limit=1")
        
        assert response.status_code == 200
        data = json.loads(response.json())
        assert "downloaded" in data
    
    def test_download_with_zero_file_limit(self, mock_s3, mock_requests):
        """Test with file_limit=0"""
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps([]).encode())
        }
        
        response = client.post("/api/s4/aircraft/download?file_limit=0")
        
        assert response.status_code == 200
        data = json.loads(response.json())
        assert data["downloaded"] == 0


class TestPrepareEndpoint:
    """Tests for POST /api/s4/aircraft/prepare"""
    
    def test_prepare_no_files_in_s3(self, mock_s3):
        """Test prepare when no files exist in S3"""
        mock_s3.list_objects_v2.return_value = {}
        
        with patch("bdi_api.s4.exercise.os.makedirs"), \
             patch("bdi_api.s4.exercise.os.listdir", return_value=[]):
            response = client.post("/api/s4/aircraft/prepare")
        
        assert response.status_code == 200
        assert "No files found" in response.json()