"""Ablage der Dokument-PDFs: in der Datenbank (Standard) oder in Azure Blob Storage.

Ein Dokument merkt sich, wo es liegt (content oder storage_key). Ein Wechsel des Backends
macht bereits abgelegte Dokumente daher nicht unlesbar.
"""
import logging
import uuid
from functools import lru_cache

from fastapi import HTTPException

from . import config

log = logging.getLogger(__name__)


@lru_cache
def _container():
    from azure.storage.blob import BlobServiceClient

    if config.AZURE_STORAGE_CONNECTION_STRING:
        service = BlobServiceClient.from_connection_string(config.AZURE_STORAGE_CONNECTION_STRING)
    elif config.AZURE_STORAGE_ACCOUNT_URL:
        from azure.identity import DefaultAzureCredential

        service = BlobServiceClient(config.AZURE_STORAGE_ACCOUNT_URL, credential=DefaultAzureCredential())
    else:
        raise RuntimeError("STORAGE_BACKEND=azure benötigt AZURE_STORAGE_ACCOUNT_URL oder "
                           "AZURE_STORAGE_CONNECTION_STRING")
    return service.get_container_client(config.AZURE_STORAGE_CONTAINER)


def store(doc, data: bytes, onboarding_id: int) -> None:
    """Legt data ab und setzt content bzw. storage_key am Dokument (Commit macht der Aufrufer)."""
    if config.STORAGE_BACKEND == "azure":
        from azure.storage.blob import ContentSettings

        key = f"onboardings/{onboarding_id}/{uuid.uuid4().hex}.pdf"
        _container().upload_blob(key, data, overwrite=False,
                                 content_settings=ContentSettings(content_type="application/pdf"))
        doc.storage_key, doc.content = key, None
    else:
        doc.content, doc.storage_key = data, None


def load(doc) -> bytes:
    if doc.storage_key:
        try:
            return _container().download_blob(doc.storage_key).readall()
        except Exception as exc:  # Blob fehlt, keine Berechtigung, Storage nicht erreichbar
            log.exception("Blob %s nicht lesbar", doc.storage_key)
            raise HTTPException(503, "Dokument ist im Moment nicht abrufbar (Dokumentenspeicher)") from exc
    return doc.content or b""


def remove(doc) -> None:
    """Löscht das Blob eines Dokuments; Fehler werden nur protokolliert (Soft Delete fängt Unfälle ab)."""
    if doc.storage_key:
        try:
            _container().delete_blob(doc.storage_key)
        except Exception:
            log.exception("Blob %s konnte nicht gelöscht werden", doc.storage_key)
