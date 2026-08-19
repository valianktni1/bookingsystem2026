from sqlalchemy import inspect, text

from .database import engine


def apply_safe_migrations() -> None:
    """Small additive migrations for installations created during Phase 1."""
    inspector = inspect(engine)
    additions = {
        "bookings": {
            "archived_at": "TIMESTAMP WITH TIME ZONE NULL" if engine.dialect.name == "postgresql" else "DATETIME NULL",
            "venue_address": "TEXT NULL",
            "venue_place_id": "VARCHAR(255) NULL",
            "venue_lat": "DOUBLE PRECISION NULL" if engine.dialect.name == "postgresql" else "REAL NULL",
            "venue_lng": "DOUBLE PRECISION NULL" if engine.dialect.name == "postgresql" else "REAL NULL",
            "legacy_import_batch": "VARCHAR(120) NULL",
            "automation_suppressed": "BOOLEAN NOT NULL DEFAULT FALSE" if engine.dialect.name == "postgresql" else "BOOLEAN NOT NULL DEFAULT 0",
            "is_test": "BOOLEAN NOT NULL DEFAULT FALSE" if engine.dialect.name == "postgresql" else "BOOLEAN NOT NULL DEFAULT 0",
        },
        "business_profiles": {
            "phone": "VARCHAR(50) NULL",
            "website": "VARCHAR(200) NULL",
        },
        "invoices": {
            "deposit_due_date": "DATE NULL",
            "due_date": "DATE NULL",
            "description": "TEXT NULL",
            "line_items": "JSON NULL" if engine.dialect.name == "postgresql" else "JSON NULL",
            "payment_schedule": "JSON NULL",
            "legacy_number": "VARCHAR(80) NULL",
            "legacy_quote_number": "VARCHAR(80) NULL",
            "legacy_source": "VARCHAR(60) NULL",
        },
        "quotes": {
            "legacy_number": "VARCHAR(80) NULL",
            "legacy_source": "VARCHAR(60) NULL",
        },
        "payments": {
            "legacy_source": "VARCHAR(60) NULL",
            "legacy_reference": "VARCHAR(160) NULL",
        },
        "documents": {
            "source_system": "VARCHAR(60) NULL",
            "legacy_document_type": "VARCHAR(80) NULL",
            "legacy_reference": "VARCHAR(160) NULL",
            "document_date": "DATE NULL",
            "is_client_visible": "BOOLEAN NOT NULL DEFAULT FALSE" if engine.dialect.name == "postgresql" else "BOOLEAN NOT NULL DEFAULT 0",
        },
        "form_submissions": {
            "submission_source": "VARCHAR(60) NOT NULL DEFAULT 'client_portal'",
            "source_document_id": "VARCHAR(36) NULL",
        },
        "contract_acceptances": {
            "acceptance_source": "VARCHAR(80) NOT NULL DEFAULT 'client_portal'",
            "source_detail": "VARCHAR(500) NULL",
            "is_legacy_import": "BOOLEAN NOT NULL DEFAULT FALSE" if engine.dialect.name == "postgresql" else "BOOLEAN NOT NULL DEFAULT 0",
            "supplier_signed_name": "VARCHAR(180) NULL",
            "supplier_signed_at": "TIMESTAMP WITH TIME ZONE NULL" if engine.dialect.name == "postgresql" else "DATETIME NULL",
            "supplier_signature_method": "VARCHAR(100) NULL",
        },
        "addon_options": {
            "is_discount": "BOOLEAN NOT NULL DEFAULT FALSE" if engine.dialect.name == "postgresql" else "BOOLEAN NOT NULL DEFAULT 0",
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
        if inspector.has_table("bookings"):
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_booking_legacy_source_id_idx "
                "ON bookings (legacy_source, legacy_id) "
                "WHERE legacy_source IS NOT NULL AND legacy_id IS NOT NULL"
            ))
