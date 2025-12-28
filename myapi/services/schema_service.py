from __future__ import annotations

from typing import Dict, List, Tuple, Any

from sqlalchemy import inspect

from myapi.config import settings
from myapi.database.connection import engine
from myapi.models.base import Base


def _normalize_type(t: object) -> str:
    s = str(t).lower().strip()
    s = " ".join(s.split())
    if any(x in s for x in ["timestamp", "datetime"]):
        return "datetime"
    if any(x in s for x in ["json", "jsonb"]):
        return "json"
    if any(x in s for x in ["varchar", "text", "string"]):
        return "string"
    if any(x in s for x in ["bigint", "integer", "smallint"]):
        return "int"
    if "numeric" in s or "decimal" in s:
        return s.replace(" ", "")
    if "uuid" in s:
        return "uuid"
    return s.replace(" ", "")


class SchemaService:
    def __init__(self) -> None:
        self._inspector = inspect(engine)
        self._schema = settings.POSTGRES_SCHEMA or None

    def check_schema(self) -> Dict[str, Any]:
        expected = {}
        for tbl in Base.metadata.sorted_tables:
            schema = tbl.schema or self._schema
            expected[(schema, tbl.name)] = tbl

        actual_tables = set(
            (self._schema, name)
            for name in self._inspector.get_table_names(schema=self._schema)
        )

        missing_tables: List[Tuple[str | None, str]] = []
        extra_tables: List[Tuple[str | None, str]] = []
        column_issues: List[str] = []

        for key, tbl in expected.items():
            if key not in actual_tables:
                missing_tables.append(key)
                continue

            schema, name = key
            db_cols = self._inspector.get_columns(name, schema=schema)
            db_cols_map = {c["name"]: c for c in db_cols}
            model_cols = {c.name: c for c in tbl.columns}

            for col_name, mcol in model_cols.items():
                if col_name not in db_cols_map:
                    column_issues.append(
                        f"[MISSING COLUMN] {schema or 'public'}.{name}.{col_name}"
                    )
                    continue
                db_type = _normalize_type(db_cols_map[col_name]["type"])  # type: ignore[index]
                model_type = _normalize_type(mcol.type)
                if db_type != model_type:
                    column_issues.append(
                        f"[TYPE MISMATCH] {schema or 'public'}.{name}.{col_name}: db={db_type}, model={model_type}"
                    )

            for col_name in db_cols_map.keys():
                if col_name not in model_cols:
                    column_issues.append(
                        f"[EXTRA COLUMN] {schema or 'public'}.{name}.{col_name}"
                    )

        for key in actual_tables:
            if key not in expected:
                extra_tables.append(key)

        ok = not missing_tables and not extra_tables and not column_issues

        return {
            "schema": self._schema or "public",
            "ok": ok,
            "missing_tables": [
                f"{s or 'public'}.{t}" for s, t in sorted(missing_tables)
            ],
            "extra_tables": [f"{s or 'public'}.{t}" for s, t in sorted(extra_tables)],
            "column_issues": column_issues,
        }

    def create_all(self) -> Dict[str, Any]:
        # Attempt to create all tables defined in metadata (idempotent)
        Base.metadata.create_all(engine)
        return self.check_schema()
