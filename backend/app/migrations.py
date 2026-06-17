from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


AGENT_CASE_COLUMNS = {
    "scene_description": "TEXT",
    "expected_result": "TEXT",
    "actual_result": "TEXT",
    "reproducible": "BOOLEAN",
    "feedback_reporter": "VARCHAR(255)",
    "responsible_owner": "VARCHAR(255)",
    "tags": "JSON",
    "closure_practice": "TEXT",
    "feedback_acceptance_conclusion": "TEXT",
}


def ensure_agent_case_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = inspector.get_columns("agent_cases")
    existing = {column["name"] for column in columns}
    missing = [(name, column_type) for name, column_type in AGENT_CASE_COLUMNS.items() if name not in existing]
    with engine.begin() as conn:
        for name, column_type in missing:
            conn.execute(text(f"ALTER TABLE agent_cases ADD COLUMN {name} {column_type}"))
        if any(name == "tags" for name, _ in missing):
            conn.execute(text("UPDATE agent_cases SET tags = '[]' WHERE tags IS NULL"))
        if engine.dialect.name == "postgresql" and "problem_type" in existing:
            result = conn.execute(
                text(
                    "SELECT data_type, udt_name FROM information_schema.columns "
                    "WHERE table_name = 'agent_cases' AND column_name = 'problem_type'"
                )
            ).mappings().first()
            if result and result["data_type"] == "USER-DEFINED":
                conn.execute(text("ALTER TABLE agent_cases ALTER COLUMN problem_type DROP DEFAULT"))
                conn.execute(
                    text(
                        "ALTER TABLE agent_cases "
                        "ALTER COLUMN problem_type TYPE VARCHAR(128) "
                        "USING problem_type::text"
                    )
                )
                conn.execute(text("ALTER TABLE agent_cases ALTER COLUMN problem_type SET DEFAULT 'other'"))
