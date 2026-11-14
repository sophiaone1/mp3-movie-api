import pandas as pd
import pytest

from src import MovieStorage
import main

MOVIE_COLUMNS = ["title", "release_year", "rating", "genre"]


# ---------- Required Part 2 tests ----------

def test_movies_persist(client, test_storage, uploaded_movies):
    other = MovieStorage(test_storage.db_path)

    df = other.get()
    assert other.count_movies() == 20
    assert len(df) == 20
    assert list(df.columns) == MOVIE_COLUMNS

    original_titles = list(pd.read_csv("fixtures/sample_movies.csv")["title"])
    assert list(df["title"]) == original_titles

    storage_ids = [row["id"] for row in other.select_columns(["title"], limit=100)]
    response = client.get("/movies", params={"limit": 100})
    api_ids = [row["id"] for row in response.json()["data"]]
    assert storage_ids == api_ids == list(range(1, 21))


def test_cache_and_processing(client, uploaded_movies, processing_body):
    # 1: first retrievals get cached
    r100 = client.get("/movies", params={"limit": 100})
    r1 = client.get("/movies", params={"limit": 1})
    assert r100.status_code == 200
    assert r1.status_code == 200
    assert main.cache.get(100) == r100.json()
    assert main.cache.get(1) == r1.json()

    # 2: repeat gives the same response
    again = client.get("/movies", params={"limit": 100})
    assert again.status_code == 200
    assert again.json() == r100.json()

    # 3: processing clears the cache
    processed = client.post("/movies/process", json=processing_body)
    assert processed.status_code == 200
    body = processed.json()
    assert body["validation_rows_removed"] == 0
    assert body["cleaning_report"] == {
        "rows_before": 20,
        "rows_after": 16,
        "rows_removed": 4,
        "columns_before": 4,
        "columns_after": 4,
        "columns_removed": 0,
    }
    assert main.cache.get(100) is None
    assert main.cache.get(1) is None

    # 4: new retrieval shows the 16 processed rows and is cached
    after = client.get("/movies", params={"limit": 100})
    assert after.status_code == 200
    after_body = after.json()
    assert after_body["total_rows"] == 16
    titles = [row["title"] for row in after_body["data"]]
    assert titles == [f"Movie {letter}" for letter in "ABCDEFGHIJKLMNOP"]
    assert [row["id"] for row in after_body["data"]] == list(range(1, 17))
    assert main.cache.get(100) == after_body


def test_cache_hit_skips_database(client, uploaded_movies, monkeypatch):
    first = client.get("/movies", params={"limit": 100})
    assert first.status_code == 200

    def fail_if_called(*args, **kwargs):
        pytest.fail("Database was called even though the response was cached")

    monkeypatch.setattr(main.storage, "select_columns", fail_if_called)
    monkeypatch.setattr(main.storage, "count_movies", fail_if_called)

    second = client.get("/movies", params={"limit": 100})
    assert second.status_code == 200
    assert second.json() == first.json()


# ---------- Part 1 tests (kept) ----------

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_upload_sample(uploaded_movies):
    assert uploaded_movies == {
        "filename": "sample_movies.csv",
        "rows": 20,
        "columns": 4,
        "column_names": MOVIE_COLUMNS,
    }


def test_upload_rejects_non_csv(client):
    response = client.post("/upload", files={"file": ("movies.txt", b"hello", "text/plain")})
    assert response.status_code == 400
    assert client.get("/health").status_code == 200


def test_upload_rejects_wrong_columns(client):
    response = client.post("/upload", files={"file": ("bad.csv", b"a,b\n1,2\n", "text/csv")})
    assert response.status_code == 400


def test_get_movies_empty(client):
    main.cache.invalidate()
    response = client.get("/movies")
    assert response.json() == {"data": [], "total_rows": 0}


def test_search_default_columns(client, uploaded_movies):
    response = client.get("/movies/search", params={"min_rating": 8.5, "limit": 2})
    assert response.json() == [
        {"id": 4, "title": "Movie C"},
        {"id": 2, "title": "Movie B"},
    ]


def test_search_title_and_rating(client, uploaded_movies):
    params = [("columns", "title"), ("columns", "rating"), ("min_rating", 8.5), ("limit", 2)]
    response = client.get("/movies/search", params=params)
    assert response.json() == [
        {"id": 4, "title": "Movie C", "rating": 9.0},
        {"id": 2, "title": "Movie B", "rating": 8.5},
    ]


def test_search_bad_column(client, uploaded_movies):
    response = client.get("/movies/search", params={"columns": "unknown"})
    assert response.status_code == 400


def test_reupload_replaces_collection(client, uploaded_movies, sample_csv_bytes):
    client.post("/upload", files={"file": ("sample_movies.csv", sample_csv_bytes, "text/csv")})
    assert client.get("/movies").json()["total_rows"] == 20


def test_process_with_no_movies(client, processing_body):
    response = client.post("/movies/process", json=processing_body)
    assert response.status_code == 400