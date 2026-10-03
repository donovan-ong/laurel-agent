"""A small web frontend for the study planner: login, chat and a profile page, in a browser instead of the CLI.

Reuses the same planner/ and tools/ code the CLI uses. Sessions are in-memory only (lost on restart), the
same trade-off already accepted by mockapi/store.py, and are independent of the CLI's file-based session —
both can be logged in at once, even as different students.
"""
