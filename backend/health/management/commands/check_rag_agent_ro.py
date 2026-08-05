# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

import psycopg2
from django.core.management.base import BaseCommand, CommandError

WRITE_PRIVILEGES = ["INSERT", "UPDATE", "DELETE", "TRUNCATE"]


class Command(BaseCommand):
    help = (
        "Connects to Postgres as the read-only rag_agent_ro role (NOT the app's "
        "own DB user) and prints every table it can see, plus which privileges "
        "it actually holds on each — to verify the read-only lockdown from "
        "db/sql/create_rag_agent_ro.sql took effect."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-write",
            action="store_true",
            help=(
                "Additionally attempt a real INSERT (inside a transaction that "
                "is always rolled back) against the first visible table, to "
                "prove writes are rejected by Postgres itself, not just absent "
                "from the catalog. Off by default since it burns a sequence "
                "value even on rollback."
            ),
        )

    def handle(self, *args, **options):
        password = os.getenv("RAG_AGENT_RO_PASSWORD")
        if not password:
            raise CommandError(
                "RAG_AGENT_RO_PASSWORD is not set. Add it to .env (matching the "
                "password used in db/sql/create_rag_agent_ro.sql) before running "
                "this command."
            )

        conn = psycopg2.connect(
            host=os.getenv("RAG_AGENT_RO_HOST", os.getenv("POSTGRES_HOST", "postgres")),
            port=os.getenv("RAG_AGENT_RO_PORT", os.getenv("POSTGRES_PORT", "5432")),
            dbname=os.getenv("RAG_AGENT_RO_DB", os.getenv("POSTGRES_DB", "college_rag")),
            user=os.getenv("RAG_AGENT_RO_USER", "rag_agent_ro"),
            password=password,
        )
        conn.autocommit = True

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT current_user, session_user;")
                current_user, session_user = cur.fetchone()
                self.stdout.write(f"Connected as: {current_user} (session_user={session_user})")

                cur.execute("SHOW default_transaction_read_only;")
                self.stdout.write(f"default_transaction_read_only: {cur.fetchone()[0]}")

                cur.execute(
                    """
                    SELECT table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                    ORDER BY table_schema, table_name;
                    """
                )
                tables = cur.fetchall()

                if not tables:
                    self.stdout.write(self.style.WARNING("No tables visible to this user."))
                    return

                self.stdout.write(f"\nTables visible to {current_user}:")
                for schema, table in tables:
                    full_name = f"{schema}.{table}"
                    granted = []
                    for priv in ["SELECT", *WRITE_PRIVILEGES]:
                        cur.execute("SELECT has_table_privilege(%s, %s);", (full_name, priv))
                        if cur.fetchone()[0]:
                            granted.append(priv)

                    unexpected_writes = [p for p in granted if p in WRITE_PRIVILEGES]
                    status = self.style.ERROR("UNEXPECTED WRITE ACCESS") if unexpected_writes else self.style.SUCCESS("OK")
                    self.stdout.write(f"  {full_name:<40} privileges: {', '.join(granted) or 'none':<30} [{status}]")

                if options["check_write"]:
                    self._check_write(cur, tables[0])
        finally:
            conn.close()

    def _check_write(self, cur, first_table):
        schema, table = first_table
        full_name = f"{schema}.{table}"
        self.stdout.write(f"\nAttempting a real INSERT into {full_name} (will be rolled back)...")
        try:
            cur.execute("BEGIN;")
            cur.execute(f"INSERT INTO {full_name} DEFAULT VALUES;")
        except psycopg2.errors.InsufficientPrivilege:
            self.stdout.write(self.style.SUCCESS("INSERT correctly rejected: insufficient privilege."))
        except psycopg2.errors.ReadOnlySqlTransaction:
            self.stdout.write(
                self.style.SUCCESS(
                    "INSERT correctly rejected: session is read-only "
                    "(default_transaction_read_only blocked it before the "
                    "table-privilege check even ran)."
                )
            )
        except psycopg2.Error as exc:
            # Any other error (e.g. a NOT NULL column with no default) still
            # proves the statement wasn't blocked purely on privilege grounds,
            # which is inconclusive rather than a pass — surface it as such.
            self.stdout.write(
                self.style.WARNING(
                    f"INSERT failed for a different reason ({exc.__class__.__name__}): "
                    f"{exc}. Privilege check inconclusive for this table."
                )
            )
        else:
            self.stdout.write(self.style.ERROR("INSERT SUCCEEDED — read-only lockdown is NOT working!"))
        finally:
            cur.execute("ROLLBACK;")
