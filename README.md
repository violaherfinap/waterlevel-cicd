# waterlevel-cicd

Pipeline ingestion data hidrologi (USGS gage height & discharge) dan meteorologi
(Open-Meteo) ke Azure Blob Storage, dijalankan oleh GitHub Actions setiap 6 jam.

## Lokal

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements-dev.txt
    pytest -q
    ruff check src tests
    python -m src.pipeline --out-dir out --lookback-days 2

## Azure

Isi `AZURE_STORAGE_ACCOUNT`, lalu login:

    az login
    $env:AZURE_STORAGE_ACCOUNT="<nama-storage>"
    python -m src.pipeline --lookback-days 2
