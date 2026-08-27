# Loading your college's records

Copyright (c) 2026 Yash Garad. All rights reserved.

This system starts **empty**. It holds no records until you load your own. This
page is how.

Everything here is a CSV file and a single command. You do not need to know SQL,
and you do not need a developer.

---

## Before you start

**Export from your existing system as CSV.** Every student information system
can do this. If yours produces Excel files, open each one and use
*File → Save As → CSV (Comma delimited)*.

> **One thing to get right before you export: dates.**
> Set your date format to **YYYY-MM-DD** (e.g. `2026-04-03`).
>
> A date written `03/04/2026` means 3 April in India and 4 March in America, and
> nothing in the file says which. The importer **refuses** those rather than
> guessing, because a date that loads cleanly and is wrong by a month is worse
> than one that fails. Dates like `25/12/2025` are accepted, because 25 cannot
> be a month.

**Work on a copy first.** Every command below defaults to a *dry run* that
changes nothing.

---

## The order matters

Some records refer to others. A faculty member belongs to a department, so the
department has to exist first. Load them in this order:

```
1. departments
2. rooms
3. programs
4. courses
5. faculty
6. students
7. fee_structures
```

If you load them out of order the importer tells you exactly what is missing —
it will not create half a record.

---

## Step 1 — Get a template

```
docker compose exec backend python manage.py import_data --entity departments --template
```

Prints the column names and one example row:

```
name,code,established_year
Computer Science,CS,1998
```

To see every entity and what each one needs:

```
docker compose exec backend python manage.py import_data --list
```

### Column names are forgiving

`Roll Number`, `roll_number`, `ROLL-NUMBER` and ` Roll  Number ` are all read as
the same column. You do **not** need to rename your export's headers to match
ours exactly — only to have a column that means the same thing.

---

## Step 2 — Check the file without changing anything

Put your CSV where the container can read it, then:

```
docker compose cp departments.csv backend:/tmp/departments.csv
docker compose exec backend python manage.py import_data \
    --entity departments --file /tmp/departments.csv --dry-run
```

You get one of two answers.

**It is fine:**

```
DRY RUN — nothing was written
  entity        : departments
  rows in file  : 42
  would be created: 42
  would be updated: 0
  unchanged     : 0

  Re-run with --apply to write these changes.
```

**Or it tells you every problem at once, with line numbers:**

```
DRY RUN — nothing was written
  rows in file  : 42
  problems      : 3

    line 7, column 'code': is required but empty
    line 19, column 'established_year': 'nineteen ninety' is not a whole number
    line 31, column 'code': duplicates line 12 (same code)

  Nothing was written.
```

Line numbers are the ones your spreadsheet shows — line 1 is the header, so
line 7 is row 7. Press **Ctrl-G** in Excel and type the number.

**Nothing is ever written when there is a problem** — not even the good rows.
A half-loaded file leaves you working out which half landed, which is worse
than a clean failure.

---

## Step 3 — Load it

Same command, with `--apply` instead of `--dry-run`:

```
docker compose exec backend python manage.py import_data \
    --entity departments --file /tmp/departments.csv --apply
```

---

## Fixing mistakes: just run it again

The importer matches each row against what is already there, using a natural
identifier:

| Entity | Matched on |
|---|---|
| departments | code |
| rooms | building + room number |
| programs | name |
| courses | code |
| faculty | email |
| students | roll number |
| fee_structures | program + semester + fee type |

So if you load 500 students, spot ten wrong email addresses, fix them in the
spreadsheet and run the whole file again, you get **ten updated and 490
unchanged** — not 500 duplicates.

This makes the safe workflow simply: fix the file, re-run it.

---

## Getting your data back out

```
docker compose exec backend python manage.py export_data --entity students --out students.csv
```

Or everything at once:

```
docker compose exec backend python manage.py export_data --all --out-dir /tmp/export
docker compose cp backend:/tmp/export ./export
```

**What comes out is exactly what goes in.** You can export, edit in a
spreadsheet, and import the result back with no changes. That round trip is
covered by automated tests, because an import path with no working export is
lock-in, and no procurement process should accept it.

Attendance, exam results and fee payments are deliberately **not** exported by
this command. They come out through a full database backup
(`scripts/backup.sh`), which is a more deliberate act by someone who has decided
it is appropriate.

---

## Deleting records

There is no bulk delete, on purpose. Removing a student's records is a decision
with consequences that a CSV file should not be able to make by accident.

Use the admin tools, or ask whoever administers the database, and take a backup
first (`scripts/backup.sh`).

---

## Making the search index match

The assistant answers descriptive questions from a search index built from your
records. After a large import, that index catches up automatically — the sync
worker notices the changes and re-indexes within a minute or two.

To confirm it has finished, open the status page:

```
https://your-server-address/api/health/status/
```

and check that the vector store row shows a document count that matches roughly
what you loaded.

---

## If something goes wrong

| What you see | What it means |
|---|---|
| `the file is missing required column(s): name` | Your export does not have a column meaning that. The message lists the columns it *did* find, and the expected format. |
| `no department matches 'Sciences'` | Spelling, or you have not imported departments yet. Matching is on the code or the full name. |
| `'03/04/2026' is ambiguous` | Re-export dates as YYYY-MM-DD. See the box at the top. |
| `is 217 characters; the maximum is 150` | A value is too long for the field. Shorten it in the spreadsheet. |
| `duplicates line 12` | The same record appears twice in one file. Delete one. |

If a problem is not on this list, send the exact command you ran and the full
output — see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for how to report it.
**Do not send the CSV file itself** if it contains real student data.

---

## A note on demo data

A fresh install is empty. If you want something to try the assistant against
before loading real records, an evaluation dataset can be switched on:

```
SEED_DEMO_DATA=true
```

in your `.env`, then restart. It only loads into an empty database and it will
never overwrite real records.

**Never enable it on a server holding real student data.** It contains 13,000
invented faculty records, and the assistant would state them as fact.

---

## Correcting a record that is already live

Re-import the corrected file. The importer matches on each entity's natural
key, so a corrected row **updates** rather than duplicating.

**One thing to know about, because it decides what students actually see.**
Answers are cached for `RESPONSE_CACHE_TTL_SECONDS` (default 30 minutes), and
they are matched **semantically** — so a student rephrasing the question does
*not* escape a stale entry. Correct a fee and, without clearing the cache,
people keep being told the old figure by a system whose whole claim is that it
answers from the records.

**A successful `--apply` clears it for you** and says so:

```
  Cached answers cleared — the next question is answered from the new records.
```

If Redis is unreachable the import still succeeds — it is already committed —
but the clearing cannot be signalled, and the importer says that instead of
claiming success. Run it yourself once Redis is back:

```bash
docker compose exec -T backend python manage.py clear_answer_cache --reason "fee correction"
```

You can also run that at any time, after correcting data by any route the
importer was not involved in.

> **Why a command and not a restart.** `docker compose up -d --force-recreate
> backend` also clears it, by throwing the process away. That works, but it
> drops in-flight answers and is a strange thing to do after a routine
> correction. The command signals every serving process instead, and returns
> non-zero if it could not — so a provisioning script can branch on it.
