# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Mirror the Postgres demo schema into the local SQL Server. DEVELOPMENT ONLY.

WHY THIS EXISTS
The real college schema is not known yet, and the one thing that is genuinely
unknown is the column names. So the T-SQL port is developed against a SQL Server
carrying the SAME SHAPE as the demo data, seeded from it, and reached through
config/schema_map.json. When the real names arrive, the map changes and this
command becomes irrelevant.

WHY THE DDL IS GENERATED RATHER THAN WRITTEN OUT
Hand-written CREATE TABLE statements are a third copy of the schema, after the
Django models and the map. It would drift, and drift here means the T-SQL path
is tested against a shape the Postgres path does not have — which would make
every comparison between the two backends meaningless. Reading
information_schema keeps one source.

SAFETY
Refuses to run unless MSSQL_MIRROR_ALLOW=yes AND the target is not the college's
production host. It DROPs and recreates tables in the target database, which is
exactly what must never happen to a college server. The read-only principal
could not do this anyway — the mirror connects as sa, deliberately, because
creating the schema is the one job that is not read-only.
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from common import schema_map

# Postgres type -> T-SQL type. Only the types the demo schema actually uses are
# mapped; anything else stops the command rather than being guessed at, because
# a silently-wrong column type produces a table that looks right and compares
# wrong.
_TYPE_MAP = {
    "bigint": "BIGINT",
    "integer": "INT",
    "smallint": "SMALLINT",
    "boolean": "BIT",
    "date": "DATE",
    "text": "NVARCHAR(MAX)",
    "double precision": "FLOAT",
    "timestamp with time zone": "DATETIMEOFFSET",
    "timestamp without time zone": "DATETIME2",
    # class_schedule holds start/end times. Added after the command refused to
    # guess, which is the behaviour working rather than a gap in it.
    "time without time zone": "TIME",
    "time with time zone": "DATETIMEOFFSET",
}


def _tsql_type(data_type, char_max_len, numeric_precision, numeric_scale):
    if data_type == "character varying":
        # NVARCHAR because college data is not guaranteed ASCII. An unbounded
        # length is used when Postgres did not state one.
        return f"NVARCHAR({char_max_len})" if char_max_len else "NVARCHAR(MAX)"
    if data_type == "character":
        return f"NCHAR({char_max_len or 1})"
    if data_type == "numeric":
        p = numeric_precision or 18
        s = numeric_scale or 0
        return f"DECIMAL({p},{s})"
    try:
        return _TYPE_MAP[data_type]
    except KeyError:
        raise CommandError(
            f"no T-SQL mapping for Postgres type {data_type!r}. Add it to "
            "_TYPE_MAP rather than letting the mirror guess: a wrong column "
            "type produces a table that looks right and compares wrong."
        ) from None


class Command(BaseCommand):
    help = "Mirror the allowlisted Postgres tables into the local SQL Server (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--rows", type=int, default=0,
                            help="Copy at most N rows per table (0 = all).")
        parser.add_argument("--schema-only", action="store_true",
                            help="Create tables without copying data.")

    def handle(self, *args, **options):
        if os.getenv("MSSQL_MIRROR_ALLOW", "").strip().lower() != "yes":
            raise CommandError(
                "refusing to run without MSSQL_MIRROR_ALLOW=yes. This command "
                "DROPs and recreates tables in the target database."
            )
        host = os.getenv("MSSQL_HOST", "mssql")
        if any(m in host.lower() for m in ("prod", "college", ".edu", ".ac.")):
            raise CommandError(
                f"MSSQL_HOST={host!r} looks like a real college server. This "
                "command drops tables; it must only ever point at a local "
                "development instance."
            )

        try:
            import pyodbc
        except ImportError as exc:
            raise CommandError(f"pyodbc is not installed: {exc}") from None

        password = os.getenv("MSSQL_SA_PASSWORD")
        if not password:
            raise CommandError("MSSQL_SA_PASSWORD is not set")

        target_db = os.getenv("MSSQL_DB", "college_records")
        dsn = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={host},{os.getenv('MSSQL_PORT', '1433')};"
            f"DATABASE={target_db};UID=sa;PWD={password};"
            # The development instance uses SQL Server's self-signed
            # certificate. TrustServerCertificate is acceptable HERE and must
            # not be carried to the college connection, where the certificate
            # is the only thing distinguishing the real server from something
            # answering on its address.
            "TrustServerCertificate=yes;Encrypt=yes"
        )

        tables = schema_map.logical_tables()
        self.stdout.write(f"mirroring {len(tables)} tables into {target_db} on {host}")

        with pyodbc.connect(dsn, autocommit=True) as mconn:
            mcur = mconn.cursor()
            for logical in tables:
                physical = schema_map.physical(logical)
                cols = self._columns(physical)
                if not cols:
                    self.stdout.write(self.style.WARNING(f"  {physical}: not in Postgres, skipped"))
                    continue
                self._create(mcur, physical, cols)
                if options["schema_only"]:
                    self.stdout.write(f"  {physical}: schema only ({len(cols)} columns)")
                    continue
                n = self._copy(mconn, mcur, physical, cols, options["rows"])
                self.stdout.write(f"  {physical}: {len(cols)} columns, {n} rows")

        self.stdout.write(self.style.SUCCESS("mirror complete"))

    def _columns(self, table):
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, data_type, character_maximum_length,
                       numeric_precision, numeric_scale, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                [table],
            )
            return cur.fetchall()

    def _create(self, mcur, table, cols):
        defs = []
        for name, dtype, clen, nprec, nscale, nullable in cols:
            tsql = _tsql_type(dtype, clen, nprec, nscale)
            defs.append(f"[{name}] {tsql} {'NULL' if nullable == 'YES' else 'NOT NULL'}")
        mcur.execute(f"IF OBJECT_ID('dbo.{table}', 'U') IS NOT NULL DROP TABLE dbo.[{table}]")
        mcur.execute(f"CREATE TABLE dbo.[{table}] ({', '.join(defs)})")

    def _copy(self, mconn, mcur, table, cols, limit):
        names = [c[0] for c in cols]
        collist = ", ".join(f"[{n}]" for n in names)
        placeholders = ", ".join("?" for _ in names)
        sql = f"SELECT {', '.join(names)} FROM {table}"
        if limit:
            sql += f" LIMIT {int(limit)}"

        with connection.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        if not rows:
            return 0
        # fast_executemany turns 13,000 single INSERTs into batched ones. Without
        # it the faculty_development copy is minutes rather than seconds.
        mcur.fast_executemany = True
        mcur.executemany(
            f"INSERT INTO dbo.[{table}] ({collist}) VALUES ({placeholders})",
            [tuple(r) for r in rows],
        )
        mconn.commit()
        return len(rows)
