import json
from pathlib import Path
from typing import Any, BinaryIO

import httpx
import pytest
from typer.testing import CliRunner

from harnessquest_sdk import cli
from harnessquest_sdk.client import HarnessQuestClient


@pytest.mark.parametrize("filename", ["session.v4.jsonl", "session.v4.jsonl.zstd"])
def test_sdk_upload_preserves_bytes_and_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str) -> None:
    path = tmp_path / filename
    content = b"session artifact\x00\xff"
    path.write_bytes(content)

    def fake_post(
        url: str, *, headers: dict[str, str], files: dict[str, tuple[str, BinaryIO, str]], timeout: int
    ) -> httpx.Response:
        assert url == "https://example.test/api/v1/sessions/upload/deepseek-jsonl"
        assert headers == {}
        assert timeout == client.timeout
        name, handle, content_type = files["file"]
        assert name == filename
        assert handle.read() == content
        assert content_type == "application/octet-stream"
        return httpx.Response(200, json={"id": "session-1"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    client = HarnessQuestClient("https://example.test/", timeout=15)

    assert client.upload_deepseek_jsonl(path) == {"id": "session-1"}


@pytest.mark.parametrize("with_case", [False, True])
@pytest.mark.parametrize("json_output", [False, True])
def test_cli_deepseek_upload_outputs_session_and_optional_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_case: bool, json_output: bool
) -> None:
    path = tmp_path / "session.v4.jsonl"
    path.write_text("session artifact", encoding="utf-8")

    class FakeClient:
        def upload_deepseek_jsonl(self, upload_path: Path) -> dict[str, str]:
            assert upload_path == path
            return {"id": "session-1", "agent_type": "deepseek_harness"}

        def create_case(self, **kwargs: Any) -> dict[str, str]:
            assert kwargs["session_id"] == "session-1"
            assert kwargs["title"] == "example case"
            return {"id": "case-1"}

    monkeypatch.setattr(cli, "_client", lambda _base_url, _token: FakeClient())
    args = ["deepseek-upload", str(path)]
    if with_case:
        args.extend(["--case-title", "example case"])
    if json_output:
        args.append("--json")

    result = CliRunner().invoke(cli.app, args)

    assert result.exit_code == 0, result.output
    if json_output:
        payload = json.loads(result.stdout)
        assert payload["session"]["id"] == "session-1"
        assert payload["case"] == ({"id": "case-1"} if with_case else None)
    else:
        assert "session-1" in result.stdout
        assert ("case-1" in result.stdout) is with_case
