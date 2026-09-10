"""Default Pre-Hire / Post-Hire / Offboarding timeline templates, offered
via the "Generate default templates" button on Timeline Templates.

The Pre-Hire/Post-Hire content isn't recovered from anywhere -- the two
templates originally set up by hand were plain database rows, never
captured in code or a migration, so a fresh deploy had nothing to
regenerate them from. This module is that missing source of truth: a
solid general-purpose checklist for each, authored fresh. Edit freely
afterward through the normal Timeline Templates UI; regenerating never
touches an already-existing template of the same name (see
templates_admin.generate_defaults).

Names are load-bearing: app/candidates.py's _instantiate_timeline() looks
up templates by the exact strings "Pre-Hire"/"Post-Hire"/"Offboarding",
so all three must keep these names.

day_offset is relative to the candidate's start date for Pre-Hire/
Post-Hire, or the employee's last day for Offboarding (negative =
before, 0 = on the day, positive = after).
"""

DEFAULT_TEMPLATES = [
    {
        "name": "Pre-Hire",
        "description": "Tasks to complete before the new hire's start date.",
        "events": [
            {
                "title": "Send offer letter and employment paperwork",
                "day_offset": -14,
                "default_assignee_role": "admin",
            },
            {
                "title": "Run background check",
                "day_offset": -10,
                "default_assignee_role": "admin",
            },
            {
                "title": "Order equipment (laptop, monitor, accessories)",
                "day_offset": -7,
                "default_assignee_role": "employee",
            },
            {
                "title": "Create IT accounts (email, Active Directory, VPN)",
                "day_offset": -5,
                "default_assignee_role": "employee",
            },
            {
                "title": "Prepare workspace and desk setup",
                "day_offset": -3,
                "default_assignee_role": "employee",
            },
            {
                "title": "Send welcome email with first-day details",
                "day_offset": -2,
                "default_assignee_role": "admin",
            },
        ],
    },
    {
        "name": "Post-Hire",
        "description": "Tasks to complete after the new hire starts.",
        "events": [
            {
                "title": "Office tour and team introductions",
                "day_offset": 0,
                "default_assignee_role": "employee",
            },
            {
                "title": "Verify IT equipment and account access",
                "day_offset": 0,
                "default_assignee_role": "employee",
            },
            {
                "title": "Complete HR paperwork and benefits enrollment",
                "day_offset": 3,
                "default_assignee_role": "admin",
            },
            {
                "title": "Security and compliance training",
                "day_offset": 5,
                "default_assignee_role": "admin",
            },
            {
                "title": "30-day check-in with manager",
                "day_offset": 30,
                "default_assignee_role": "admin",
            },
            {
                "title": "90-day performance review",
                "day_offset": 90,
                "default_assignee_role": "admin",
            },
        ],
    },
    {
        "name": "Offboarding",
        "description": "Tasks to complete around an employee's departure.",
        "events": [
            {
                "title": "Notify manager and team of departure",
                "day_offset": -5,
                "default_assignee_role": "admin",
            },
            {
                "title": "Schedule exit interview",
                "day_offset": -3,
                "default_assignee_role": "admin",
            },
            {
                "title": "Notify IT to prepare for account deactivation",
                "day_offset": -2,
                "default_assignee_role": "admin",
            },
            {
                "title": "Collect company equipment (laptop, badge, etc.)",
                "day_offset": 0,
                "default_assignee_role": "employee",
            },
            {
                "title": "Revoke building and office access",
                "day_offset": 0,
                "default_assignee_role": "admin",
            },
            {
                "title": "Deactivate email and IT accounts",
                "day_offset": 0,
                "default_assignee_role": "admin",
            },
            {
                "title": "Remove from distribution lists and shared systems",
                "day_offset": 1,
                "default_assignee_role": "admin",
            },
            {
                "title": "Process final paycheck and benefits paperwork",
                "day_offset": 5,
                "default_assignee_role": "admin",
            },
        ],
    },
]
