#!/usr/bin/env python3
"""Generate the README contribution calendar SVG from GitHub contribution data."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


GRAPHQL_URL = "https://api.github.com/graphql"
OUTPUT_PATH = Path("assets/contribution-calendar.svg")

EMPTY_COLOR = "#1f2937"
ACTIVE_COLOR = "#ffffff"
TEXT_COLOR = "#767676"
FONT_FAMILY = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif, "
    "'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol'"
)


def iso_datetime(day: dt.date) -> str:
    return f"{day.isoformat()}T00:00:00Z"


def iso_end_datetime(day: dt.date) -> str:
    return f"{day.isoformat()}T23:59:59Z"


def fetch_contributions(username: str, token: str, start: dt.date, end: dt.date) -> dict[str, int]:
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    payload = {
        "query": query,
        "variables": {
            "login": username,
            "from": iso_datetime(start),
            "to": iso_end_datetime(end),
        },
    }
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "contribution-calendar-updater",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub GraphQL request failed: {error.code} {details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"GitHub GraphQL request failed: {error.reason}") from error

    if response_data.get("errors"):
        raise RuntimeError(json.dumps(response_data["errors"], indent=2))

    user = response_data.get("data", {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user not found: {username}")

    days: dict[str, int] = {}
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    for week in weeks:
        for day in week["contributionDays"]:
            days[day["date"]] = int(day["contributionCount"])

    return days


def text_style(font_size: int, display_none: bool = False) -> str:
    style = (
        f"fill:{TEXT_COLOR};text-anchor:start;text-align:center;font-family:{FONT_FAMILY};"
        f"white-space:nowrap;font-size:{font_size}px;"
    )
    if display_none:
        style += "display:none;"
    return style


def render_calendar(contributions: dict[str, int], start: dt.date, end: dt.date) -> str:
    start_sunday = start - dt.timedelta(days=(start.weekday() + 1) % 7)
    total_days = (end - start_sunday).days + 1
    week_count = (total_days + 6) // 7
    width = 27 + ((week_count - 1) * 12) + 12

    parts = [
        '<?xml version="1.0" standalone="no"?>\n',
        '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
        '"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">',
        '<svg role="img" aria-label="GitHub contribution calendar: dark gray means no '
        'contributions, white means contributions" version="1.1" '
        'xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="104">',
    ]

    for weekday in range(7):
        for week in range(week_count):
            day = start_sunday + dt.timedelta(days=(week * 7) + weekday)
            if day > end:
                continue

            count = contributions.get(day.isoformat(), 0)
            fill = ACTIVE_COLOR if count > 0 else EMPTY_COLOR
            x = 27 + (week * 12)
            y = 20 + (weekday * 12)
            parts.append(
                f'<rect style="fill:{fill};shape-rendering:crispedges;" '
                f'data-score="{count}" data-date="{day.isoformat()}" x="{x}" y="{y}" '
                'width="10" height="10"/>'
            )

    weekday_labels = [
        ("Sun", 28, True),
        ("Mon", 40, False),
        ("Tue", 52, True),
        ("Wed", 64, False),
        ("Thu", 77, True),
        ("Fri", 89, False),
        ("Sat", 101, True),
    ]
    for label, y, hidden in weekday_labels:
        parts.append(f'<text style="{text_style(9, hidden)}" x="0" y="{y}">{label}</text>')

    last_month = ""
    for week in range(week_count):
        day = start_sunday + dt.timedelta(days=week * 7)
        if day > end:
            continue
        month = day.strftime("%b")
        if day.month != start_sunday.month and month != last_month:
            parts.append(
                f'<text style="{text_style(10)}" x="{27 + (week * 12)}" y="10">{month}</text>'
            )
            last_month = month

    parts.append("</svg>")
    return "".join(parts)


def main() -> int:
    username = os.environ.get("GITHUB_USERNAME", "boojamesgabriel-ops")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("GITHUB_TOKEN or GH_TOKEN is required.", file=sys.stderr)
        return 1

    today = dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=365)
    contributions = fetch_contributions(username, token, start, today)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render_calendar(contributions, start, today), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
