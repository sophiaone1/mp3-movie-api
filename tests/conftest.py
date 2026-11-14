from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from src import MovieStorage

SAMPLE_CSV = Path(__file__).parent.parent / "fixtures" / "sample_movies.csv"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client that uses a temporary database instead of data/movies.db."""
    monkeypatch.setattr(main, "storage", MovieStorage(tmp_path / "test.db"))
    return TestClient(main.app)


@pytest.fixture
def upload_sample(client):
    """Upload the sample CSV and return the response."""
    def _upload():
        with open(SAMPLE_CSV, "rb") as f:
            return client.post(
                "/upload", files={"file": ("sample_movies.csv", f, "text/csv")}
            )
    return _upload