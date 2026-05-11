#!/usr/bin/env python3
"""Sync Canvas due dates from an iCal feed into Google Calendar."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo


DEFAULT_ENV = ".env"
DEFAULT_TITLE_PREFIX = "Canvas Due:"


@dataclass(frozen=True)
class CanvasDeadline:
    uid: str
    title: str
    due_at: dt.datetime
    url: str = ""
    course: str = ""
    description: str = ""


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def csv_env(name: str, default: str) -> List[str]:
    value = os.environ.get(name, default)
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def unfold_ics_lines(text: str) -> List[str]:
    lines: List[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def parse_property(line: str) -> Optional[Tuple[str, Dict[str, str], str]]:
    if ":" not in line:
        return None
    left, value = line.split(":", 1)
    parts = left.split(";")
    name = parts[0].upper()
    params: Dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, param_value = part.split("=", 1)
            params[key.upper()] = param_value.strip('"')
    return name, params, value


def unescape_ics(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def parse_ics_datetime(value: str, params: Dict[str, str], default_tz: ZoneInfo) -> Optional[dt.datetime]:
    if not value:
        return None
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
        parsed_date = dt.datetime.strptime(value[:8], "%Y%m%d").date()
        return dt.datetime.combine(parsed_date, dt.time(23, 59), tzinfo=default_tz)

    timezone = default_tz
    if value.endswith("Z"):
        value = value[:-1]
        timezone = dt.timezone.utc
    elif "TZID" in params:
        try:
            timezone = ZoneInfo(params["TZID"])
        except Exception:
            timezone = default_tz

    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            parsed = dt.datetime.strptime(value, fmt)
            if timezone is dt.timezone.utc:
                return parsed.replace(tzinfo=timezone).astimezone(default_tz)
            return parsed.replace(tzinfo=timezone).astimezone(default_tz)
        except ValueError:
            continue
    return None


def vevent_blocks(ics_text: str) -> Iterable[List[str]]:
    block: List[str] = []
    in_event = False
    for line in unfold_ics_lines(ics_text):
        if line.upper() == "BEGIN:VEVENT":
            in_event = True
            block = []
            continue
        if line.upper() == "END:VEVENT" and in_event:
            yield block
            in_event = False
            block = []
            continue
        if in_event:
            block.append(line)


def event_props(block: Sequence[str]) -> Dict[str, List[Tuple[Dict[str, str], str]]]:
    props: Dict[str, List[Tuple[Dict[str, str], str]]] = {}
    for line in block:
        parsed = parse_property(line)
        if not parsed:
            continue
        name, params, value = parsed
        props.setdefault(name, []).append((params, unescape_ics(value)))
    return props


def first_prop(props: Dict[str, List[Tuple[Dict[str, str], str]]], name: str) -> Tuple[Dict[str, str], str]:
    values = props.get(name.upper()) or []
    if not values:
        return {}, ""
    return values[0]


def normalize_uid(uid: str, title: str, due_at: dt.datetime, url: str) -> str:
    if uid:
        return uid
    stable = "|".join([url, title, due_at.isoformat()])
    return "generated-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r"\s+\[(?:https?:)?//[^\\]]*$", "", title)
    title = re.sub(r"\s*\[[^\]]*(?:https?:)?//[^\]]*\]\s*", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def split_title_course(title: str) -> Tuple[str, str]:
    match = re.search(r"\s+\[([A-Z0-9_]+_SP\d+_[A-Z0-9]+)\]\s*$", title)
    if not match:
        return title, ""
    return title[: match.start()].strip(), match.group(1)


def extract_course(
    props: Dict[str, List[Tuple[Dict[str, str], str]]],
    description: str,
    fallback: str = "",
) -> str:
    if fallback:
        return fallback
    categories = []
    for _, value in props.get("CATEGORIES", []):
        categories.extend(part.strip() for part in value.split(",") if part.strip())
    for category in categories:
        if "http" in category.lower():
            continue
        category = clean_title(category).strip(" []")
        if category:
            return category
    for line in description.splitlines():
        if line.lower().startswith("course:") and ":" in line:
            return line.split(":", 1)[1].strip()
    return ""


def should_include(deadline: CanvasDeadline, include_keywords: Sequence[str], exclude_keywords: Sequence[str]) -> bool:
    haystack = " ".join([deadline.title, deadline.url, deadline.course, deadline.description]).lower()
    if any(keyword in haystack for keyword in exclude_keywords):
        return False
    if any(marker in deadline.url for marker in ("/assignments/", "/quizzes/", "/discussion_topics/")):
        return True
    return any(keyword in haystack for keyword in include_keywords)


def parse_canvas_deadlines(
    ics_text: str,
    timezone_name: str,
    include_keywords: Sequence[str],
    exclude_keywords: Sequence[str],
) -> List[CanvasDeadline]:
    default_tz = ZoneInfo(timezone_name)
    deadlines: List[CanvasDeadline] = []
    for block in vevent_blocks(ics_text):
        props = event_props(block)
        dt_params, dt_value = first_prop(props, "DTSTART")
        due_at = parse_ics_datetime(dt_value, dt_params, default_tz)
        if due_at is None:
            dt_params, dt_value = first_prop(props, "DTEND")
            due_at = parse_ics_datetime(dt_value, dt_params, default_tz)
        if due_at is None:
            continue

        _, title = first_prop(props, "SUMMARY")
        title = clean_title(title)
        title, course_from_title = split_title_course(title)
        _, uid = first_prop(props, "UID")
        _, url = first_prop(props, "URL")
        _, description = first_prop(props, "DESCRIPTION")
        course = extract_course(props, description, course_from_title)
        deadline = CanvasDeadline(
            uid=normalize_uid(uid, title, due_at, url),
            title=title,
            due_at=due_at,
            url=url,
            course=course,
            description=description,
        )
        if should_include(deadline, include_keywords, exclude_keywords):
            deadlines.append(deadline)
    return sorted(deadlines, key=lambda item: item.due_at)


def fetch_canvas_feed(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "canvas-deadline-sync/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def require_google_service(token_file: Path, client_secrets_file: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise SystemExit(
            "Missing Google dependencies. Run: python3 -m pip install -r requirements.txt"
        ) from exc

    scopes = ["https://www.googleapis.com/auth/calendar.events"]
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not client_secrets_file.exists():
                raise SystemExit(
                    f"Missing Google OAuth client file: {client_secrets_file}\n"
                    "Create it in Google Cloud Console, or update GOOGLE_CLIENT_SECRETS_FILE."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_file), scopes)
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return build("calendar", "v3", credentials=creds)


def event_body(
    deadline: CanvasDeadline,
    duration_minutes: int,
    reminder_minutes: Sequence[int],
    timezone_name: str,
    title_prefix: str = DEFAULT_TITLE_PREFIX,
) -> Dict[str, object]:
    end_at = deadline.due_at + dt.timedelta(minutes=duration_minutes)
    description_parts = [
        f"Canvas assignment synced from {deadline.url or 'Canvas calendar feed'}.",
        f"Canvas UID: {deadline.uid}",
    ]
    if deadline.course:
        description_parts.append(f"Course: {deadline.course}")
    if deadline.description:
        description_parts.append("")
        description_parts.append(deadline.description)
    return {
        "summary": f"{title_prefix} {deadline.title}",
        "description": "\n".join(description_parts),
        "start": {"dateTime": deadline.due_at.isoformat(), "timeZone": timezone_name},
        "end": {"dateTime": end_at.isoformat(), "timeZone": timezone_name},
        "transparency": "transparent",
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": minutes} for minutes in reminder_minutes],
        },
        "extendedProperties": {
            "private": {
                "canvas_uid": deadline.uid,
                "canvas_deadline_sync": "true",
            }
        },
    }


def find_existing_event(service, calendar_id: str, deadline: CanvasDeadline) -> Optional[Dict[str, object]]:
    response = (
        service.events()
        .list(
            calendarId=calendar_id,
            privateExtendedProperty=f"canvas_uid={deadline.uid}",
            singleEvents=True,
            maxResults=10,
        )
        .execute()
    )
    items = response.get("items", [])
    return items[0] if items else None


def upsert_deadline(
    service,
    calendar_id: str,
    deadline: CanvasDeadline,
    duration_minutes: int,
    reminder_minutes: Sequence[int],
    timezone_name: str,
) -> str:
    body = event_body(deadline, duration_minutes, reminder_minutes, timezone_name)
    existing = find_existing_event(service, calendar_id, deadline)
    if existing:
        service.events().update(calendarId=calendar_id, eventId=existing["id"], body=body).execute()
        return "updated"
    service.events().insert(calendarId=calendar_id, body=body).execute()
    return "created"


def filter_window(deadlines: Sequence[CanvasDeadline], now: dt.datetime, lookahead_days: int) -> List[CanvasDeadline]:
    end = now + dt.timedelta(days=lookahead_days)
    return [deadline for deadline in deadlines if now <= deadline.due_at <= end]


def reminder_minutes_from_env() -> List[int]:
    values = os.environ.get("REMINDER_MINUTES", "1440,60")
    minutes: List[int] = []
    for value in values.split(","):
        value = value.strip()
        if value:
            minutes.append(int(value))
    return minutes or [1440, 60]


def print_deadlines(deadlines: Sequence[CanvasDeadline]) -> None:
    if not deadlines:
        print("No Canvas deadlines found in the configured window.")
        return
    for deadline in deadlines:
        course = f" [{deadline.course}]" if deadline.course else ""
        print(f"- {deadline.due_at:%a %b %-d, %Y %-I:%M %p}: {deadline.title}{course}")


def deadlines_to_json(deadlines: Sequence[CanvasDeadline]) -> str:
    payload = [
        {
            "uid": deadline.uid,
            "title": deadline.title,
            "course": deadline.course,
            "due_at": deadline.due_at.isoformat(),
            "url": deadline.url,
        }
        for deadline in deadlines
    ]
    return json.dumps(payload, indent=2)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Sync Canvas iCal due dates into Google Calendar.")
    parser.add_argument("--env", default=DEFAULT_ENV, help="Path to env file. Default: .env")
    parser.add_argument("--apply", action="store_true", help="Actually create/update Google Calendar events.")
    parser.add_argument("--ics-file", help="Read an exported Canvas .ics file instead of fetching the feed.")
    parser.add_argument("--json", action="store_true", help="Print deadlines as JSON for automations.")
    args = parser.parse_args(argv)

    load_env_file(Path(args.env))
    timezone_name = os.environ.get("TIMEZONE", "America/Los_Angeles")
    include_keywords = csv_env(
        "INCLUDE_KEYWORDS",
        "assignment,quiz,discussion,exam,paper,reflection,submission,lecture engagement,bluebook",
    )
    exclude_keywords = csv_env("EXCLUDE_KEYWORDS", "office hours,ta oh,zoom online meeting")

    if args.ics_file:
        ics_text = Path(args.ics_file).read_text(encoding="utf-8")
    else:
        feed_url = os.environ.get("CANVAS_CALENDAR_FEED_URL", "").strip()
        if not feed_url:
            raise SystemExit("Set CANVAS_CALENDAR_FEED_URL in .env before running this.")
        ics_text = fetch_canvas_feed(feed_url)

    deadlines = parse_canvas_deadlines(ics_text, timezone_name, include_keywords, exclude_keywords)
    now = dt.datetime.now(ZoneInfo(timezone_name))
    lookahead_days = int(os.environ.get("LOOKAHEAD_DAYS", "120"))
    deadlines = filter_window(deadlines, now, lookahead_days)

    if args.json:
        print(deadlines_to_json(deadlines))
        return 0

    if not args.apply:
        print("Dry run. Use --apply to write to Google Calendar.")
        print_deadlines(deadlines)
        return 0

    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
    duration_minutes = int(os.environ.get("EVENT_DURATION_MINUTES", "30"))
    reminders = reminder_minutes_from_env()
    token_file = Path(os.environ.get("GOOGLE_TOKEN_FILE", "secrets/google_token.json"))
    client_secrets_file = Path(os.environ.get("GOOGLE_CLIENT_SECRETS_FILE", "secrets/google_client_secret.json"))
    service = require_google_service(token_file, client_secrets_file)

    counts = {"created": 0, "updated": 0}
    for deadline in deadlines:
        result = upsert_deadline(service, calendar_id, deadline, duration_minutes, reminders, timezone_name)
        counts[result] += 1
        print(f"{result}: {deadline.title} ({deadline.due_at:%Y-%m-%d %H:%M})")
    print(f"Done. Created {counts['created']}, updated {counts['updated']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
