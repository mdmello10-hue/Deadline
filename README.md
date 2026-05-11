# Deadline

Sync Canvas assignment due dates into Google Calendar.

## What It Does

- Reads your Canvas Calendar Feed URL.
- Finds assignments, quizzes, discussions, exams, papers, and similar deadline items.
- Skips obvious calendar noise such as TA office hours.
- Creates or updates Google Calendar events with:
  - 24-hour reminder
  - 1-hour reminder
  - transparent/free status so deadline events do not block your calendar

## Setup

1. Copy the example env file:

   ```bash
   cp .env.example .env
   ```

2. In Canvas, copy your calendar feed URL:

   `Calendar > Calendar Feed`

3. Paste it into `.env`:

   ```bash
   CANVAS_CALENDAR_FEED_URL=...
   ```

4. Install dependencies:

   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

5. Add Google OAuth credentials at:

   ```text
   secrets/google_client_secret.json
   ```

   The first real sync opens a Google sign-in page and saves a reusable token at
   `secrets/google_token.json`.

## Run

Preview what would sync:

```bash
.venv/bin/python sync_canvas_deadlines.py
```

Write to Google Calendar:

```bash
.venv/bin/python sync_canvas_deadlines.py --apply
```

## Google Calendar Auth

To write to Google Calendar, create an OAuth desktop client in Google Cloud and
download the JSON file to:

```text
secrets/google_client_secret.json
```

The first `--apply` run opens a browser approval flow. After approval, the script
saves a local token to:

```text
secrets/google_token.json
```

Both files are ignored by Git.

## Daily Automation

After the first successful `--apply` run, schedule the command below with cron,
launchd, or your preferred task runner:

```bash
cd /path/to/Deadline
.venv/bin/python sync_canvas_deadlines.py --apply --env .env
```

The script is safe to run repeatedly. It stores the Canvas UID on each calendar
event and updates existing matching events instead of creating duplicates.

## Security Notes

Do not commit `.env`, `.venv/`, or `secrets/`. The included `.gitignore` keeps
Canvas feed URLs, Google OAuth files, and local tokens out of the repository.
