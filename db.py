from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    and_,
    create_engine,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.engine import Engine, RowMapping


BASE_DIR = Path(__file__).resolve().parent
metadata = MetaData()

leads_table = Table(
    "leads",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=True),
    Column("phone", Text, nullable=False, unique=True),
    Column("profile_name", Text, nullable=True),
    Column("requirement", Text, nullable=True),
    Column("appointment_datetime", Text, nullable=True),
    Column("conversation_state", Text, nullable=False, default="NEW"),
    Column("lead_status", Text, nullable=False, default="new"),
    Column("source", Text, nullable=False, default="whatsapp"),
    Column("last_user_message", Text, nullable=True),
    Column("last_bot_message", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

messages_table = Table(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("phone", Text, nullable=False),
    Column("direction", Text, nullable=False),
    Column("message", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)

Index("idx_leads_phone", leads_table.c.phone)
Index("idx_leads_status", leads_table.c.lead_status)
Index("idx_leads_appointment_datetime", leads_table.c.appointment_datetime)
Index("idx_messages_phone", messages_table.c.phone)

_engine: Engine | None = None


def timestamp_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_database_url(database_url: str) -> str:
    clean_url = database_url.strip()

    if clean_url.startswith("postgres://"):
        return f"postgresql+psycopg://{clean_url[len('postgres://'):]}"

    if clean_url.startswith("postgresql://"):
        return f"postgresql+psycopg://{clean_url[len('postgresql://'):]}"

    if clean_url.startswith("sqlite:///"):
        raw_path = clean_url[len("sqlite:///"):]
        if raw_path == ":memory:":
            return clean_url

        path_obj = Path(raw_path)
        if not path_obj.is_absolute():
            path_obj = BASE_DIR / path_obj
        return f"sqlite:///{path_obj.resolve().as_posix()}"

    return clean_url


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return normalize_database_url(database_url)

    db_path = Path(os.getenv("DATABASE_PATH", "leads.db"))
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    return f"sqlite:///{db_path.resolve().as_posix()}"


def get_engine() -> Engine:
    global _engine

    if _engine is not None:
        return _engine

    database_url = get_database_url()
    engine_kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}

    if database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}

    _engine = create_engine(database_url, **engine_kwargs)
    return _engine


def row_to_dict(row: RowMapping | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def init_db() -> None:
    database_url = get_database_url()
    if database_url.startswith("sqlite:///"):
        sqlite_path = Path(database_url[len("sqlite:///"):])
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    metadata.create_all(get_engine())


def get_lead_by_phone(phone: str) -> dict[str, Any] | None:
    statement = select(leads_table).where(leads_table.c.phone == phone)
    with get_engine().connect() as conn:
        row = conn.execute(statement).mappings().first()
    return row_to_dict(row)


def get_or_create_lead(phone: str, profile_name: str = "") -> dict[str, Any]:
    existing = get_lead_by_phone(phone)
    if existing:
        if profile_name and not existing.get("profile_name"):
            update_lead(phone, profile_name=profile_name)
            existing["profile_name"] = profile_name
        return existing

    now = timestamp_now()
    statement = insert(leads_table).values(
        phone=phone,
        profile_name=profile_name or None,
        conversation_state="NEW",
        lead_status="new",
        source="whatsapp",
        created_at=now,
        updated_at=now,
    )

    with get_engine().begin() as conn:
        conn.execute(statement)

    lead = get_lead_by_phone(phone)
    return lead if lead is not None else {}


def update_lead(phone: str, **fields: Any) -> dict[str, Any] | None:
    clean_fields = dict(fields)
    if not clean_fields:
        return get_lead_by_phone(phone)

    clean_fields["updated_at"] = timestamp_now()
    statement = update(leads_table).where(leads_table.c.phone == phone).values(**clean_fields)

    with get_engine().begin() as conn:
        conn.execute(statement)

    return get_lead_by_phone(phone)


def log_message(phone: str, direction: str, message: str) -> None:
    statement = insert(messages_table).values(
        phone=phone,
        direction=direction,
        message=message,
        created_at=timestamp_now(),
    )
    with get_engine().begin() as conn:
        conn.execute(statement)


def list_leads(search: str = "", lead_status: str = "All", source: str = "All") -> list[dict[str, Any]]:
    filters: list[Any] = []

    if search:
        search_term = f"%{search.lower()}%"
        filters.append(
            or_(
                func.lower(func.coalesce(leads_table.c.name, "")).like(search_term),
                func.lower(func.coalesce(leads_table.c.profile_name, "")).like(search_term),
                func.lower(func.coalesce(leads_table.c.phone, "")).like(search_term),
                func.lower(func.coalesce(leads_table.c.requirement, "")).like(search_term),
            )
        )

    if lead_status and lead_status.lower() != "all":
        filters.append(func.lower(leads_table.c.lead_status) == lead_status.lower())

    if source and source.lower() != "all":
        filters.append(func.lower(leads_table.c.source) == source.lower())

    statement = select(leads_table)
    if filters:
        statement = statement.where(and_(*filters))
    statement = statement.order_by(leads_table.c.updated_at.desc())

    with get_engine().connect() as conn:
        rows = conn.execute(statement).mappings().all()

    return [dict(row) for row in rows]


def list_appointments(search: str = "", upcoming_only: bool = False) -> list[dict[str, Any]]:
    filters: list[Any] = [leads_table.c.appointment_datetime.is_not(None)]

    if search:
        search_term = f"%{search.lower()}%"
        filters.append(
            or_(
                func.lower(func.coalesce(leads_table.c.name, "")).like(search_term),
                func.lower(func.coalesce(leads_table.c.phone, "")).like(search_term),
                func.lower(func.coalesce(leads_table.c.requirement, "")).like(search_term),
            )
        )

    if upcoming_only:
        filters.append(leads_table.c.appointment_datetime >= datetime.now().strftime("%Y-%m-%d %H:%M"))

    statement = select(leads_table).where(and_(*filters)).order_by(leads_table.c.appointment_datetime.asc())

    with get_engine().connect() as conn:
        rows = conn.execute(statement).mappings().all()

    return [dict(row) for row in rows]


def get_dashboard_metrics() -> dict[str, int]:
    with get_engine().connect() as conn:
        total_leads = conn.execute(select(func.count()).select_from(leads_table)).scalar_one()
        booked_appointments = conn.execute(
            select(func.count()).select_from(leads_table).where(leads_table.c.appointment_datetime.is_not(None))
        ).scalar_one()
        pending_leads = conn.execute(
            select(func.count()).select_from(leads_table).where(leads_table.c.conversation_state != "CONFIRMED")
        ).scalar_one()
        whatsapp_leads = conn.execute(
            select(func.count()).select_from(leads_table).where(leads_table.c.source == "whatsapp")
        ).scalar_one()

    return {
        "total_leads": int(total_leads),
        "booked_appointments": int(booked_appointments),
        "pending_leads": int(pending_leads),
        "whatsapp_leads": int(whatsapp_leads),
    }


def add_manual_lead(
    name: str,
    phone: str,
    requirement: str,
    appointment_datetime: str | None = None,
) -> dict[str, Any] | None:
    existing = get_lead_by_phone(phone)
    now = timestamp_now()

    if existing:
        final_appointment = appointment_datetime or existing.get("appointment_datetime")
        lead_status = "booked" if final_appointment else "qualified"
        state = "CONFIRMED" if final_appointment else "ASK_APPOINTMENT"
        return update_lead(
            phone,
            name=name,
            requirement=requirement,
            appointment_datetime=final_appointment,
            conversation_state=state,
            lead_status=lead_status,
            source="manual",
        )

    statement = insert(leads_table).values(
        name=name,
        phone=phone,
        requirement=requirement,
        appointment_datetime=appointment_datetime,
        conversation_state="CONFIRMED" if appointment_datetime else "ASK_APPOINTMENT",
        lead_status="booked" if appointment_datetime else "qualified",
        source="manual",
        created_at=now,
        updated_at=now,
    )

    with get_engine().begin() as conn:
        conn.execute(statement)

    return get_lead_by_phone(phone)
