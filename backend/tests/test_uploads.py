from types import SimpleNamespace
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_current_user
from app.main import app
from app.routes import uploads as upload_routes

BASE = "/api/v1/uploads"
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
DEFAULT_MAX_IMAGE_UPLOAD_SIZE_MB = 20


class _FakeStorage:
    stored: ClassVar[list[tuple[str, bytes, str | None]]] = []

    def put_binary(self, key: str, content: bytes, content_type: str | None = None) -> None:
        self.stored.append((key, content, content_type))

    def get_binary(self, key: str) -> tuple[bytes, str]:
        return b"image", "image/png"


@pytest.fixture(autouse=True)
def _patch_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeStorage.stored = []
    monkeypatch.setattr(upload_routes, "ObjectStorage", _FakeStorage)


@pytest.fixture
def image_upload_client(client: TestClient) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="test-admin-id")
    return client


def test_image_upload_default_limit_allows_files_up_to_20mb(image_upload_client: TestClient) -> None:
    payload = b"\x89PNG\r\n\x1a\n" + (b"a" * (11 * 1024 * 1024))

    response = image_upload_client.post(
        f"{BASE}/images",
        files={"file": ("large.png", payload, "image/png")},
    )

    assert response.status_code == HTTP_OK
    assert response.json()["url"].startswith("/api/v1/uploads/images/")
    assert len(_FakeStorage.stored) == 1
    assert _FakeStorage.stored[0][1] == payload


def test_image_upload_rejects_files_above_configured_limit(
    image_upload_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upload_routes, "get_settings", lambda: SimpleNamespace(max_image_upload_size_mb=1))
    payload = b"\x89PNG\r\n\x1a\n" + (b"a" * (1024 * 1024))

    response = image_upload_client.post(
        f"{BASE}/images",
        files={"file": ("too-large.png", payload, "image/png")},
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert response.json()["detail"] == "Image exceeds maximum size of 1 MB"
    assert _FakeStorage.stored == []


def test_default_image_upload_limit_is_20mb() -> None:
    assert Settings().max_image_upload_size_mb == DEFAULT_MAX_IMAGE_UPLOAD_SIZE_MB
