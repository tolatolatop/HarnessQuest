import json
import os
from pathlib import Path

import typer
from rich import print as rich_print

from harnessquest_sdk.client import HarnessQuestClient

app = typer.Typer(help="Upload AI agent sessions to HarnessQuest.")


def _client(base_url: str, token: str | None) -> HarnessQuestClient:
    return HarnessQuestClient(base_url=base_url, token=token or os.getenv("HARNESSQUEST_TOKEN"))


@app.command()
def login(
    base_url: str = typer.Option("http://localhost:8000", envvar="HARNESSQUEST_BASE_URL"),
    username: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True),
) -> None:
    client = HarnessQuestClient(base_url)
    token = client.login(username, password)
    rich_print("[green]Login succeeded.[/green]")
    rich_print(f"export HARNESSQUEST_TOKEN={token}")


@app.command()
def upload(
    path: Path = typer.Argument(..., exists=True),
    base_url: str = typer.Option("http://localhost:8000", envvar="HARNESSQUEST_BASE_URL"),
    token: str | None = typer.Option(None, envvar="HARNESSQUEST_TOKEN"),
) -> None:
    client = _client(base_url, token)
    paths = sorted(path.glob("*.json")) if path.is_dir() else [path]
    for item in paths:
        result = client.upload_file(item)
        rich_print(f"[green]uploaded[/green] {item} -> session {result['id']}")


@app.command("case-create")
def case_create(
    title: str = typer.Option(...),
    session_id: str | None = typer.Option(None),
    base_url: str = typer.Option("http://localhost:8000", envvar="HARNESSQUEST_BASE_URL"),
    token: str | None = typer.Option(None, envvar="HARNESSQUEST_TOKEN"),
) -> None:
    client = _client(base_url, token)
    result = client.create_case(title=title, session_id=session_id, source="offline_log_import")
    rich_print(json.dumps(result, ensure_ascii=False, indent=2))
