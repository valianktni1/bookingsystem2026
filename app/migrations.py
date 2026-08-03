from sqlalchemy import inspect, text

from .database import engine


def apply_safe_migrations() -> None:
    """Small additive migrations for installations created during Phase 1."""
    inspector = inspect(engine)
    additions = {
        "bookings": {
            "archived_at": "TIMESTAMP WITH TIME ZONE NULL" if engine.dialect.name == "postgresql" else "DATETIME NULL",
        },
        "business_profiles": {
            "phone": "VARCHAR(50) NULL",
            "website": "VARCHAR(200) NULL",
        },
        "invoices": {
            "due_date": "DATE NULL",
            "description": "TEXT NULL",
            "line_items": "JSON NULL" if engine.dialect.name == "postgresql" else "JSON NULL",
        },
    }
    with engine.begin() as connection:
        for table, columns in additions.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
