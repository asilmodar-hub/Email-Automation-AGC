"""Paths that are too long for Windows.

Windows refuses an ordinary path of 260 characters or more. A contact list
inside a synced SharePoint or OneDrive library reaches that sooner than anyone
expects.
"""
import os
import sys

LONG_PREFIX = "\\\\?\\"


def long_path(path):
    """The same path in the form Windows accepts at any length."""
    path = os.path.abspath(path)
    if sys.platform == "win32" and len(path) > 200 and not path.startswith(LONG_PREFIX):
        return LONG_PREFIX + path
    return path
