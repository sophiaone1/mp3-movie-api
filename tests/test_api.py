def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_upload_sample(upload_sample):
    response = upload_sample()
    assert response.status_code == 200
    assert response.json() == {
        "filename": "sample_movies.csv",
        "rows": 20,
        "columns": 4,
        "column_names": ["title", "release_year", "rating", "genre"],
    }


def test_upload_rejects_non_csv(client):
    response = client.post("/upload", files={"file": ("movies.txt", b"hello", "text/plain")})
    assert response.status_code == 400
    assert client.get("/health").status_code == 200


def test_upload_rejects_wrong_columns(client):
    response = client.post("/upload", files={"file": ("bad.csv", b"a,b\n1,2\n", "text/csv")})
    assert response.status_code == 400


def test_get_movies_empty(client):
    response = client.get("/movies")
    assert response.json() == {"data": [], "total_rows": 0}


def test_get_movies_limit(client, upload_sample):
    upload_sample()
    body = client.get("/movies", params={"limit": 2}).json()
    assert body["total_rows"] == 20
    assert len(body["data"]) == 2
    assert body["data"][0]["id"] == 1
    assert body["data"][0]["title"] == "Movie A"


def test_search_default_columns(client, upload_sample):
    upload_sample()
    response = client.get("/movies/search", params={"min_rating": 8.5, "limit": 2})
    assert response.json() == [
        {"id": 4, "title": "Movie C"},
        {"id": 2, "title": "Movie B"},
    ]


def test_search_title_and_rating(client, upload_sample):
    upload_sample()
    params = [("columns", "title"), ("columns", "rating"), ("min_rating", 8.5), ("limit", 2)]
    response = client.get("/movies/search", params=params)
    assert response.json() == [
        {"id": 4, "title": "Movie C", "rating": 9.0},
        {"id": 2, "title": "Movie B", "rating": 8.5},
    ]


def test_search_bad_column(client, upload_sample):
    upload_sample()
    response = client.get("/movies/search", params={"columns": "director"})
    assert response.status_code == 400


def test_reupload_replaces_collection(client, upload_sample):
    upload_sample()
    upload_sample()
    assert client.get("/movies").json()["total_rows"] == 20


def test_process_with_no_movies(client):
    response = client.post("/movies/process", json={})
    assert response.status_code in (400, 422)