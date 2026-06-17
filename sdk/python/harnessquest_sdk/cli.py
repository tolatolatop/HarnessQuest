import json
import os
from pathlib import Path

import typer
from rich import print as rich_print

from harnessquest_sdk.client import HarnessQuestClient
from harnessquest_sdk.converters import convert_claude_jsonl

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


@app.command("claude-convert")
def claude_convert(
    path: Path = typer.Argument(..., exists=True),
    output: Path | None = typer.Option(None, "--output", "-o"),
    project_name: str | None = typer.Option(None),
    user_email: str | None = typer.Option(None),
) -> None:
    payload = convert_claude_jsonl(path, project_name=project_name, user_email=user_email)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output:
        output.write_text(text + "\n", encoding="utf-8")
        rich_print(f"[green]converted[/green] {path} -> {output}")
    else:
        rich_print(text)


@app.command("claude-upload")
def claude_upload(
    path: Path = typer.Argument(..., exists=True),
    project_name: str | None = typer.Option(None),
    user_email: str | None = typer.Option(None),
    case_title: str | None = typer.Option(None),
    base_url: str = typer.Option("http://localhost:8000", envvar="HARNESSQUEST_BASE_URL"),
    token: str | None = typer.Option(None, envvar="HARNESSQUEST_TOKEN"),
) -> None:
    client = _client(base_url, token)
    payload = convert_claude_jsonl(path, project_name=project_name, user_email=user_email)
    session = client.import_session(payload)
    rich_print(f"[green]uploaded claude jsonl[/green] {path} -> session {session['id']}")
    if case_title:
        case = client.create_case(
            title=case_title,
            session_id=session["id"],
            source="offline_log_import",
            severity="medium",
            problem_type="other",
        )
        rich_print(f"[green]created case[/green] {case['id']}")


@app.command("opencode-upload")
def opencode_upload(
    path: Path = typer.Argument(..., exists=True),
    case_title: str | None = typer.Option(None),
    base_url: str = typer.Option("http://localhost:8000", envvar="HARNESSQUEST_BASE_URL"),
    token: str | None = typer.Option(None, envvar="HARNESSQUEST_TOKEN"),
) -> None:
    client = _client(base_url, token)
    session = client.upload_opencode_json(path)
    rich_print(f"[green]uploaded opencode json[/green] {path} -> session {session['id']}")
    if case_title:
        case = client.create_case(
            title=case_title,
            session_id=session["id"],
            source="offline_log_import",
            severity="medium",
            problem_type="other",
        )
        rich_print(f"[green]created case[/green] {case['id']}")


@app.command("auto-upload")
def auto_upload(
    path: Path = typer.Argument(..., exists=True),
    case_title: str | None = typer.Option(None),
    base_url: str = typer.Option("http://localhost:8000", envvar="HARNESSQUEST_BASE_URL"),
    token: str | None = typer.Option(None, envvar="HARNESSQUEST_TOKEN"),
) -> None:
    client = _client(base_url, token)
    session = client.upload_auto(path)
    rich_print(f"[green]uploaded auto-detected session[/green] {path} -> session {session['id']} ({session['agent_type']})")
    if case_title:
        case = client.create_case(
            title=case_title,
            session_id=session["id"],
            source="offline_log_import",
            severity="medium",
            problem_type="other",
        )
        rich_print(f"[green]created case[/green] {case['id']}")


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


if __name__ == "__main__":
    app()
