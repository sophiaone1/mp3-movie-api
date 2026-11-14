# MP3 Movie API

This project is a FastAPI application that stores one movie collection in a SQLite database and caches repeated movie retrievals. Uploading a CSV through `POST /upload` validates that it has exactly the `title`, `release_year`, `rating`, and `genre` columns, then replaces the stored collection. The `src/database.py` module creates the SQLite connection and the `movies` table, while `src/storage.py` handles saving, reading, counting, and filtering movies with SQL queries. `GET /movies` returns stored movies with a total count, and `GET /movies/search` filters by minimum rating and sorts results by rating using SQL. The `src/cache.py` module uses FakeRedis to cache `GET /movies` responses for 90 seconds, keyed by the `limit` value. `POST /movies/process` reuses the MP1 data pipeline to validate and clean the stored data, then saves the result back to SQLite. After every successful upload or processing step, the cache is cleared so later requests never return outdated data. Because the data lives in SQLite, it is still available after the server restarts.

## Running the API

```bash
python -m uvicorn main:app --reload
```

Then open http://127.0.0.1:8000/docs.

## Running the Tests

```bash
python -m pytest tests -v
```

## Sample Processing Request

After uploading `fixtures/sample_movies.csv`, send this body to `POST /movies/process`:

```json
{
  "validation": {
    "required_columns": ["title", "release_year", "rating", "genre"],
    "numeric_columns": ["release_year", "rating"]
  },
  "processing": {
    "remove_duplicates": true,
    "missing": {"enabled": true, "axis": "rows"},
    "outliers": {
      "enabled": true,
      "columns": ["rating"],
      "method": "iqr",
      "threshold": 1.5
    }
  }
}
```

Expected result:

```json
{
  "validation_rows_removed": 0,
  "cleaning_report": {
    "rows_before": 20,
    "rows_after": 16,
    "rows_removed": 4,
    "columns_before": 4,
    "columns_after": 4,
    "columns_removed": 0
  }
}
```