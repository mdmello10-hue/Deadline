# Deadline

Sync Canvas and Slack due dates into Google Calendar.

## What It Does

- Reads your Canvas Calendar Feed URL.
- Optionally scans selected Slack channels for due dates and event times.
- Finds assignments, quizzes, discussions, exams, papers, events, and similar deadline items.
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

4. Optional: add Slack.

   Create a Slack app or token with read access to the channels you want to scan,
   invite the app to those channels if needed, and fill in:

   ```bash
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_CHANNEL_IDS=C012ABCDEF,C987ZYXWVU
   ```

   Slack channel IDs are available from each channel's profile/details panel.
   Keep the token in `.env`; do not commit it.

   For multiple Slack workspaces, use one source per workspace:

   ```bash
   SLACK_SOURCES=TCG,PBL,CORNERSTONE
   SLACK_TCG_BOT_TOKEN=xoxb-...
   SLACK_TCG_CHANNEL_IDS=C012ABCDEF,C987ZYXWVU
   SLACK_PBL_BOT_TOKEN=xoxb-...
   SLACK_PBL_CHANNEL_IDS=C111ABCDEF
   SLACK_CORNERSTONE_BOT_TOKEN=xoxb-...
   SLACK_CORNERSTONE_CHANNEL_IDS=C222ABCDEF
   ```

5. Install dependencies:

   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

6. Add Google OAuth credentials at:

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

The script is safe to run repeatedly. It stores a stable deadline UID on each
calendar event and updates existing matching events instead of creating
duplicates.

## Security Notes

Do not commit `.env`, `.venv/`, or `secrets/`. The included `.gitignore` keeps
Canvas feed URLs, Slack tokens, Google OAuth files, and local tokens out of the repository.
