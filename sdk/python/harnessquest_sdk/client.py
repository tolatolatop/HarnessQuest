from pathlib import Path
from typing import Any

import httpx


class HarnessQuestClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def login(self, username: str, password: str) -> str:
        response = httpx.post(
            f"{self.base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = _json_object(response)
        token = data.get("access_token")
        if not isinstance(token, str):
            raise ValueError("Login response did not include access_token")
        self.token = token
        return self.token

    def import_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/api/v1/sessions/import",
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _json_object(response)

    def upload_file(self, path: str | Path) -> dict[str, Any]:
        with Path(path).open("rb") as handle:
            response = httpx.post(
                f"{self.base_url}/api/v1/sessions/upload",
                headers=self.headers,
                files={"file": (Path(path).name, handle, "application/json")},
                timeout=self.timeout,
            )
        response.raise_for_status()
        return _json_object(response)

    def upload_opencode_json(self, path: str | Path) -> dict[str, Any]:
        with Path(path).open("rb") as handle:
            response = httpx.post(
                f"{self.base_url}/api/v1/sessions/upload/opencode-json",
                headers=self.headers,
                files={"file": (Path(path).name, handle, "application/json")},
                timeout=self.timeout,
            )
        response.raise_for_status()
        return _json_object(response)

    def create_case(self, title: str, session_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = {"title": title, "session_id": session_id, **kwargs}
        response = httpx.post(
            f"{self.base_url}/api/v1/cases",
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _json_object(response)

    def get_case(self, case_id: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/api/v1/cases/{case_id}",
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _json_object(response)


def _json_object(response: httpx.Response) -> dict[str, Any]:
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object response")
    return data
