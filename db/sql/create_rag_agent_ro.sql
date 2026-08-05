-- Copyright (c) 2026 Yash Garad. All rights reserved.

-- ============================================================================
-- Read-only Postgres role for the RAG agent.
--
-- WHAT THIS DOES:
--   - Creates (or resets the flags on) a login role `rag_agent_ro` that:
--       * cannot create databases, roles, or replicate
--       * defaults every session to a read-only transaction (defense in depth,
--         on top of the grants below — belt and suspenders)
--       * has USAGE on the `public` schema but no privileges on any table
--         until explicitly granted below
--       * gets SELECT on the whitelisted tables ONLY — nothing else, no
--         wildcard grants, no future-table auto-grants
--
-- YOU DO NOT NORMALLY NEED TO RUN THIS. The backend applies exactly these
-- statements on every startup via `manage.py setup_readonly_role` (see
-- backend/academics/management/commands/setup_readonly_role.py), reading the
-- password from RAG_AGENT_RO_PASSWORD in .env. This file is the reference
-- copy / manual fallback.
--
-- NO PASSWORD IS WRITTEN IN THIS FILE, deliberately — the secret lives only in
-- .env (which is gitignored). The password is passed in as a psql variable.
--
-- HOW TO RUN MANUALLY (from the repo root, with the stack up):
--   docker compose exec -T postgres psql -U postgres -d college_rag \
--     -v pw="$RAG_AGENT_RO_PASSWORD" -f - < db/sql/create_rag_agent_ro.sql
--
-- Never replace :'pw' below with a literal password — that would put a live
-- secret into a file that gets copied, committed, and shared.
-- ============================================================================

\if :{?pw}
\else
    \echo 'ERROR: no password supplied. Re-run with -v pw="$RAG_AGENT_RO_PASSWORD"'
    \quit 1
\endif

-- Create only if missing. Done with psql's \if rather than a DO $$ block
-- because psql does NOT interpolate :'pw' inside dollar-quoted strings — the
-- variable would be sent to the server verbatim and fail.
SELECT NOT EXISTS (
    SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rag_agent_ro'
) AS role_missing \gset

\if :role_missing
CREATE ROLE rag_agent_ro LOGIN PASSWORD :'pw';
\endif

-- Keep the password in sync with .env even if the role already existed.
ALTER ROLE rag_agent_ro LOGIN PASSWORD :'pw';

ALTER ROLE rag_agent_ro
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    CONNECTION LIMIT 10;

-- Session-level default is a separate ALTER ROLE ... SET statement in Postgres
-- (can't be combined with the role-attribute clauses above).
ALTER ROLE rag_agent_ro SET default_transaction_read_only = on;

-- Lock down the schema itself: PUBLIC (i.e. every role, by default) loses
-- the implicit CREATE/USAGE it gets on a fresh database. rag_agent_ro then
-- gets USAGE explicitly, and only USAGE — it can look up objects, not create them.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE college_rag TO rag_agent_ro;
GRANT USAGE ON SCHEMA public TO rag_agent_ro;

-- Clean slate: strip any privileges this role may already have on every
-- table in the schema, so re-running this script never leaves stale grants
-- around if a table gets removed from the whitelist later.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM rag_agent_ro;

-- ----------------------------------------------------------------------------
-- General institutional data ONLY — no per-student records. The agent's job
-- is general Q&A (courses offered, departments, faculty, timetable, fee
-- structure), not lookups tied to an individual student's identity.
--
-- Deliberately EXCLUDED (per-student / sensitive — see backend/academics/models.py):
--   students, enrollments, attendance, exam_results, fee_payments
-- Also excluded: Django's own auth_*/django_* tables (not college data at all).
-- ----------------------------------------------------------------------------
GRANT SELECT ON
    public.departments,
    public.faculty,
    public.programs,
    public.courses,
    public.courses_prerequisites,
    public.course_offerings,
    public.rooms,
    public.class_schedule,
    public.exam_timetable,
    public.fee_structure
TO rag_agent_ro;

-- No GRANT on sequences, functions, or other schemas — SELECT on the
-- whitelisted tables is the entire privilege surface for this role.

-- Sanity check: list what rag_agent_ro can now see (run separately or as
-- the last statement here; safe to leave in since it's read-only itself).
SELECT grantee, table_schema, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'rag_agent_ro'
ORDER BY table_schema, table_name;
