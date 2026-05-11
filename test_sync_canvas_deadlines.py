import datetime as dt
import unittest

from sync_canvas_deadlines import parse_canvas_deadlines


SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:assignment-1
SUMMARY:Week 6 Quiz
DTSTART;TZID=America/Los_Angeles:20260513T235900
URL:https://canvas.ucsd.edu/courses/1/quizzes/2
DESCRIPTION:Course: ECON 5
END:VEVENT
BEGIN:VEVENT
UID:office-hours-1
SUMMARY:TA Office Hours
DTSTART;TZID=America/Los_Angeles:20260513T150000
URL:https://canvas.ucsd.edu/calendar
DESCRIPTION:Zoom Online Meeting
END:VEVENT
BEGIN:VEVENT
UID:discussion-1
SUMMARY:Week 7 Discussion
DTSTART;VALUE=DATE:20260518
URL:https://canvas.ucsd.edu/courses/1/discussion_topics/3
DESCRIPTION:Course: GSS 27
END:VEVENT
END:VCALENDAR
"""


class CanvasDeadlineParserTest(unittest.TestCase):
    def test_parses_assignments_and_skips_office_hours(self):
        deadlines = parse_canvas_deadlines(
            SAMPLE_ICS,
            "America/Los_Angeles",
            ["assignment", "quiz", "discussion"],
            ["office hours", "zoom online meeting"],
        )
        self.assertEqual([item.title for item in deadlines], ["Week 6 Quiz", "Week 7 Discussion"])
        self.assertEqual(deadlines[0].due_at.hour, 23)
        self.assertEqual(deadlines[0].course, "ECON 5")
        self.assertEqual(deadlines[1].due_at, dt.datetime(2026, 5, 18, 23, 59, tzinfo=deadlines[1].due_at.tzinfo))


if __name__ == "__main__":
    unittest.main()
