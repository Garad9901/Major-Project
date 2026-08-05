# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging
import time
from datetime import datetime

import psycopg2
from psycopg2 import sql

import config
import state as state_module
import vector_store
from chunker import row_to_text
from embedder import embed_text
from lookups import fetch_department_lookup
from poller import poll_table
from queue_writer import append_changes
from vector_store import upsert_point

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sync_worker] %(levelname)s: %(message)s",
)
logger = logging.getLogger("sync_worker")


def connect():
    return psycopg2.connect(**config.DB_CONFIG)


def embed_and_upsert_changes(table, changes, dept_lookup):
    for change in changes:
        try:
            text = row_to_text(table, change["row"], dept_lookup)
            vector = embed_text(text)
            upsert_point(table, change["pk"], vector, text, change["updated_at"])
            logger.info("embedded %s id=%s -> %s", table, change["pk"], text[:80])
        except Exception:
            # One bad row/embedding call shouldn't take down the whole cycle —
            # it'll simply be retried next cycle since the watermark for this
            # table only advances after this loop finishes successfully.
            logger.exception("failed to embed/upsert %s id=%s", table, change["pk"])
            raise


def reconcile_deletions(conn, descriptive_tables):
    """Delete index entries whose source row no longer exists.

    WHY THIS IS NEEDED
    Change detection is watermark-based: `WHERE updated_at >= <last seen>`. A
    DELETED row does not have a later updated_at — it simply stops appearing in
    the result set. Nothing in a watermark poll can observe an absence, so a
    deleted row's vector previously stayed in Qdrant permanently and remained
    retrievable, with no way to remove it short of rebuilding the collection.

    That is not a cosmetic leak. It means a withdrawn course, a corrected fee
    description or a removed staff profile keeps being fed to the model as
    current fact. It was found in exactly that state: a deliberately poisoned
    test record ('INJ999: Advanced Injection Studies') had been deleted from
    Postgres a week earlier, yet its vector — carrying a prompt-injection
    payload — was still live in the index and still retrievable.

    Deletions are rare, so this compares id sets rather than maintaining
    tombstones: no schema change, and it self-heals drift from any cause,
    including rows removed while this worker was not running.
    """
    removed_total = 0
    for table in descriptive_tables:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT id FROM {}").format(sql.Identifier(table)))
            live_ids = {row[0] for row in cur.fetchall()}

        indexed = vector_store.indexed_row_ids(table)
        orphans = [pid for row_id, pid in indexed.items() if row_id not in live_ids]

        if orphans:
            vector_store.delete_points(orphans)
            removed_total += len(orphans)
            logger.warning(
                "reconcile: removed %d orphaned index entr%s for %s "
                "(row deleted in Postgres but still searchable)",
                len(orphans), "y" if len(orphans) == 1 else "ies", table,
            )
    return removed_total


def run_cycle(conn, app_state, poll_tables, descriptive_tables):
    total_changes = 0
    dept_lookup = fetch_department_lookup(conn)

    for table in poll_tables:
        entry = app_state.get(table, {})
        is_descriptive = table in descriptive_tables

        # A table's watermark records how far it has been POLLED, which is not
        # the same as how far it has been EMBEDDED. Polling advances the
        # watermark whether or not the table is descriptive, so a table that
        # becomes descriptive later (added to config.DESCRIPTIVE_TABLES) would
        # have its pre-existing rows stranded forever: already behind the
        # watermark, so never re-fetched, and never embedded because they were
        # polled back when the table was not descriptive.
        #
        # This is not hypothetical — it happened when
        # faculty_development_profiles was introduced: 55 rows were polled by a
        # worker still running the old config, and the restarted worker with the
        # new config then reported "no changes" forever while Qdrant held zero
        # of them.
        #
        # So the state now also records whether the table was being embedded
        # when its watermark was written. If that has just become true, rewind
        # to the epoch and re-embed the table from scratch. Safe to do: point
        # IDs are a deterministic uuid5 of (table, pk), so re-embedding
        # overwrites points rather than duplicating them.
        if is_descriptive and entry and not entry.get("embedded", False):
            logger.warning(
                "%s is now a descriptive table but its existing watermark was "
                "written before it was — rewinding to re-embed it from scratch.",
                table,
            )
            entry = {}

        last_updated_at = datetime.fromisoformat(entry.get("last_updated_at", state_module.EPOCH))
        seen_ids = set(entry.get("seen_ids_at_last_ts", []))

        changes, new_last_updated_at, new_seen_ids = poll_table(conn, table, last_updated_at, seen_ids)

        if changes:
            for change in changes:
                logger.info(
                    "%-18s %-8s id=%-5s updated_at=%s",
                    table, change["op"], change["pk"], change["updated_at"],
                )
            append_changes(changes)
            total_changes += len(changes)

            if table in descriptive_tables:
                embed_and_upsert_changes(table, changes, dept_lookup)

        app_state[table] = {
            "last_updated_at": new_last_updated_at.isoformat(),
            "seen_ids_at_last_ts": sorted(new_seen_ids),
            # Whether this watermark was advanced by a cycle that also embedded.
            # Read on the next cycle by the rewind check above.
            "embedded": is_descriptive,
        }
        # Persist after every table, not just at the end of the cycle, so a
        # crash mid-cycle doesn't re-process tables already handled this run.
        state_module.save_state(app_state)

    if total_changes:
        logger.info("poll cycle complete: %d change(s) detected", total_changes)
    else:
        logger.info("poll cycle complete: no changes detected")


def main():
    logger.info("sync_worker starting")
    logger.info("poll interval: %ds", config.POLL_INTERVAL_SECONDS)

    app_state = state_module.load_state()

    # Which tables to poll is DISCOVERED from the grants this role actually
    # holds, not hard-coded here — see the long note in config.py. Rediscovered
    # on every cycle rather than once at startup so that a table granted (or
    # revoked) later is picked up without restarting the worker; it is two cheap
    # catalogue queries against an already-open connection.
    while True:
        try:
            conn = connect()
            try:
                poll_tables, excluded = config.discover_tables(conn)

                # Log the full picture only when it changes, so a steady-state
                # worker does not repeat the same inventory every 30 seconds.
                signature = (tuple(poll_tables), tuple(excluded))
                if signature != main._last_signature:
                    config.log_discovery(poll_tables, excluded)
                    main._last_signature = signature

                descriptive = [t for t in config.DESCRIPTIVE_TABLES if t in poll_tables]
                run_cycle(conn, app_state, poll_tables, descriptive)

                # Deletions cannot be seen by a watermark poll, so they are
                # reconciled separately. Not every cycle: it scans the whole
                # collection, and deletions are rare compared with edits.
                # Cycle 0 (startup) always runs, so a restart repairs drift
                # that accumulated while the worker was down.
                if main._cycle % config.RECONCILE_EVERY_N_CYCLES == 0:
                    reconcile_deletions(conn, descriptive)
                main._cycle += 1
            finally:
                conn.close()
        except psycopg2.Error as exc:
            logger.error("database error during poll cycle: %s", exc)
        except Exception:
            logger.exception("unexpected error during poll cycle")

        time.sleep(config.POLL_INTERVAL_SECONDS)


# Sentinel for the "inventory changed" check above; never equal to a real
# (poll_tables, excluded) pair, so the first cycle always logs.
main._last_signature = None

# Counts poll cycles so reconciliation can run periodically rather than every
# cycle. Starts at 0 so the first cycle after any start always reconciles.
main._cycle = 0


if __name__ == "__main__":
    main()
