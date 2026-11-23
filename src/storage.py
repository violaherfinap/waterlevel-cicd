"""Tujuan penyimpanan: Azure Blob Storage atau folder lokal (untuk uji lokal)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)


class BlobSink(Protocol):
    def upload(self, name: str, body: bytes) -> str: ...


class LocalBlobSink:
    """Meniru struktur blob di disk, dipakai untuk ``--out-dir`` dan pytest."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def upload(self, name: str, body: bytes) -> str:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return str(path)


class AzureBlobSink:
    """Upload ke ``https://<account>.blob.core.windows.net/<container>``.

    Autentikasi memakai ``DefaultAzureCredential``: di GitHub Actions credential
    ini otomatis menjadi ``WorkloadIdentityCredential`` setelah ``azure/login``.
    """

    def __init__(self, account: str, container: str) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        self.account = account
        self.container = container
        self._service = BlobServiceClient(
            account_url=f"https://{account}.blob.core.windows.net",
            credential=DefaultAzureCredential(),
        )
        self._client = self._service.get_container_client(container)

    def upload(self, name: str, body: bytes) -> str:
        self._client.upload_blob(name=name, data=body, overwrite=True)
        return f"https://{self.account}.blob.core.windows.net/{self.container}/{name}"


def encode(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
