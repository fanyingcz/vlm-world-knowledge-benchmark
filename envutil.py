"""Environment variable helpers.

Why this module exists
----------------------
Windows environment variables are case-insensitive, so a variable set as
``mysql_password`` is readable as ``MYSQL_PASSWORD``. Linux and macOS are
case-sensitive, so the same code would silently read ``None`` there.

We therefore check both spellings explicitly, which keeps the project portable
across Windows workstations and Linux servers / CI.

Security note
-------------
No credential is ever hardcoded here, and ``require_env`` deliberately raises
instead of falling back to a default value. A silent default is exactly how
secrets end up committed to version control.
"""

import os


def get_env(name, default=None):
    """Read an environment variable, tolerating case differences."""
    value = os.getenv(name)
    if value is None:
        value = os.getenv(name.lower())
    if value is None:
        value = os.getenv(name.upper())
    return default if value is None else value


def require_env(name):
    """Read a mandatory environment variable, or fail loudly at startup."""
    value = get_env(name)
    if value is None or not value.strip():
        raise RuntimeError(
            f"Missing required environment variable: {name}\n"
            f"\n"
            f"Set it before starting the app.  PowerShell:\n"
            f'    $env:{name} = "your-value"\n'
            f"\n"
            f"Persist it for future sessions:\n"
            f'    setx {name} "your-value"\n'
            f"\n"
            f"See .env.example for the full list of required variables."
        )
    return value
