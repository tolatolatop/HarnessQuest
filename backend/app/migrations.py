from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


AGENT_CASE_COLUMNS = {
    "scene_description": "TEXT",
    "expected_result": "TEXT",
    "actual_result": "TEXT",
    "reproducible": "BOOLEAN",
    "responsible_owner": "VARCHAR(255)",
    "tags": "JSON",
    "closure_practice": "TEXT",
    "feedback_acceptance_conclusion": "TEXT",
}


def ensure_agent_case_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    existing = {column["name"] for column in inspector.get_columns("agent_cases")}
    missing = [(name, column_type) for name, column_type in AGENT_CASE_COLUMNS.items() if name not in existing]
    if not missing:
        return
    with engine.begin() as conn:
        for name, column_type in missing:
            conn.execute(text(f"ALTER TABLE agent_cases ADD COLUMN {name} {column_type}"))
        if any(name == "tags" for name, _ in missing):
            conn.execute(text("UPDATE agent_cases SET tags = '[]' WHERE tags IS NULL"))
