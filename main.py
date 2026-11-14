import io
import logging
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from data_pipeline import create_cleaning_report, process_data, validate_dataframe
from src import (
    HealthResponse,
    ProcessConfig,
    MovieStorage,
    MovieUploadInfo,
    MovieDataResponse,
    MovieProcessingReport,
    log_requests,
    setup_logging,
)
from src.storage import MOVIE_COLUMNS

setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Data Processing API", version="1.0.0")
app.middleware("http")(log_requests)
storage = MovieStorage()


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return the application status and version."""
    return HealthResponse(status="ok", version="1.0.0")


@app.post("/upload", response_model=MovieUploadInfo)
async def upload_movies(file: UploadFile = File(...)):
    """Read a CSV upload and replace the stored movie collection."""
    # TODO 1: MP2's .csv check and parsing
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".csv":
        logger.warning("Unsupported file format: %s", suffix)
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except pd.errors.EmptyDataError:
        logger.warning("Empty CSV upload: %s", file.filename)
        raise HTTPException(status_code=400, detail="The CSV file is empty.")
    except pd.errors.ParserError as e:
        logger.warning("CSV parse error for %s: %s", file.filename, e)
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")
    except UnicodeDecodeError:
        logger.warning("Could not decode %s as text", file.filename)
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text.")

    # TODO 2: quick validation before saving
    if sorted(df.columns) != sorted(MOVIE_COLUMNS):
        logger.warning("Wrong columns in %s: %s", file.filename, list(df.columns))
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have exactly these columns: {MOVIE_COLUMNS}",
        )
    if df.empty:
        logger.warning("No data rows in %s", file.filename)
        raise HTTPException(status_code=400, detail="The CSV has no data rows.")

    df = df[MOVIE_COLUMNS]

    # TODO 3: replace the current collection
    storage.save(df)
    logger.info("Uploaded movies: filename=%s, rows=%d", file.filename, len(df))
    return {
        "filename": file.filename,
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns),
    }


@app.get("/movies", response_model=MovieDataResponse)
def get_movies(limit: int = Query(default=100, ge=1)):
    """Return up to limit stored movies and the total count."""
    data = storage.select_columns(MOVIE_COLUMNS, limit=limit)
    total_rows = storage.count_movies()
    logger.info("Retrieved movies: returned_rows=%d, total_rows=%d", len(data), total_rows)
    return {"data": data, "total_rows": total_rows}


@app.get("/movies/search", response_model=list[dict])
def query_movies(
    columns: list[str] = Query(default=["title"]),
    min_rating: float = Query(default=0, ge=0, le=10),
    limit: int = Query(default=100, ge=1),
):
    """Return id plus selected fields for movies with rating >= min_rating."""
    try:
        results = storage.query_movies(columns, min_rating, limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    logger.info(
        "Queried movies: columns=%s, min_rating=%s, returned_rows=%d",
        columns, min_rating, len(results),
    )
    return results


@app.post("/movies/process", response_model=MovieProcessingReport)
def process_movies(config: ProcessConfig):
    """Validate and process the stored movies using MP1 functions."""
    # TODO 1: get the stored data
    df = storage.get()
    if df.empty:
        logger.warning("No movies stored to process")
        raise HTTPException(status_code=400, detail="No movies stored. Upload a CSV first.")

    # TODO 2: reuse MP2's processing logic
    config_dict = config.model_dump()
    required = config.validation.required_columns
    numeric = config.validation.numeric_columns

    try:
        for col in numeric:
            if col not in df.columns:
                raise ValueError(f"Numeric column '{col}' not found in dataset")

        validated_df = validate_dataframe(df, required, numeric)
        validation_rows_removed = len(df) - len(validated_df)
        validated_copy = validated_df.copy()

        processed_df = process_data(validated_df, config_dict)
        cleaning_report = create_cleaning_report(validated_copy, processed_df)
    except ValueError as error:
        logger.warning("Processing failed: %s", error)
        raise HTTPException(status_code=400, detail=str(error))

    # TODO 3: save the processed data
    storage.save(processed_df)
    logger.info(
        "Processed movies: validation_removed=%d, rows_before=%d, rows_after=%d",
        validation_rows_removed,
        len(validated_copy),
        len(processed_df),
    )
    return {
        "validation_rows_removed": validation_rows_removed,
        "cleaning_report": cleaning_report,
    }