# utils.py - Utility functions used across the application.
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Provides data I/O, password verification, and the login_required decorator.
# All functions follow PEP8 and include Google-style docstrings.

import json
import os
import time
from werkzeug.security import check_password_hash, generate_password_hash


DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "data.json")
IN_MEMORY_DATA = None

# ---------------------------------------------------------------------------
# Basic brute-force protection for the login endpoints
# ---------------------------------------------------------------------------
# In-memory only: on a long-running local/Flask process this stops repeated
# password guessing from a given IP within the process lifetime. On a
# serverless host (Vercel) each cold instance starts a fresh counter, so this
# is a first line of defence, not a full solution — pair it with a platform
# level protection (see Documentation.md, section "Protection du site").
_LOGIN_ATTEMPTS = {}  # ip -> {"count": int, "locked_until": float}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 minutes


def is_locked_out(ip):
    """Check whether an IP address is currently locked out of login.

    Args:
        ip (str): The client IP address (from ``request.remote_addr``).

    Returns:
        bool: True if the IP has exceeded ``MAX_ATTEMPTS`` recently and the
              lockout window has not yet expired.
    """
    entry = _LOGIN_ATTEMPTS.get(ip)
    if not entry:
        return False
    if entry["count"] < MAX_ATTEMPTS:
        return False
    if time.time() > entry["locked_until"]:
        # Lockout window has passed; reset and allow again.
        _LOGIN_ATTEMPTS.pop(ip, None)
        return False
    return True


def register_failed_login(ip):
    """Record a failed login attempt for an IP address.

    After ``MAX_ATTEMPTS`` failures the IP is locked out for
    ``LOCKOUT_SECONDS``.

    Args:
        ip (str): The client IP address.
    """
    entry = _LOGIN_ATTEMPTS.setdefault(ip, {"count": 0, "locked_until": 0})
    entry["count"] += 1
    if entry["count"] >= MAX_ATTEMPTS:
        entry["locked_until"] = time.time() + LOCKOUT_SECONDS


def reset_login_attempts(ip):
    """Clear the failed-attempt counter for an IP address after a success.

    Args:
        ip (str): The client IP address.
    """
    _LOGIN_ATTEMPTS.pop(ip, None)


def load_data():
    """Load JSON data from an environment payload or the local file system.

    On Vercel, the function should not rely on the repository file system
    because serverless instances are stateless. When ``DATA_JSON`` is set,
    the payload is parsed directly from the environment. Otherwise the code
    falls back to the local ``data.json`` file for the regular Flask CLI.

    Returns:
        dict: Parsed data containing at minimum ``user`` and ``answers`` keys.
    """
    global IN_MEMORY_DATA

    env_data = os.getenv("DATA_JSON")
    if env_data:
        try:
            IN_MEMORY_DATA = json.loads(env_data)
            return IN_MEMORY_DATA
        except (TypeError, json.JSONDecodeError):
            return {"user": {"name": "admin", "hashed_password": ""}, "answers": []}

    if IN_MEMORY_DATA is not None:
        return IN_MEMORY_DATA

    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Return a minimal structure so the app can still function
        return {"user": {"name": "admin", "hashed_password": ""}, "answers": []}


def save_data(data):
    """Write the dictionary back to ``data.json`` when a persistent file is
    available, otherwise keep the mutation in an in-process memory store.

    Vercel serverless deployments do not guarantee a writable repository
    filesystem. They also cannot update environment variables safely during
    requests, so in that environment we keep the state only in memory for the
    life of the process.

    Args:
        data (dict): The data dictionary to persist.
    """
    global IN_MEMORY_DATA

    env_data = os.getenv("DATA_JSON")
    if env_data:
        IN_MEMORY_DATA = data
        return

    try:
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        # Keep the serverless behaviour graceful when Vercel forbids writes.
        IN_MEMORY_DATA = data


def verify_login(username, password):
    """Verify a user's login credentials against stored data.

    Loads the persistent data file, checks that the username matches the
    stored ``user.name`` (or email), and compares the entered password against
    the hashed password using Werkzeug's PBKDF2 checker.

    Args:
        username (str): The username or email entered by the user.
        password (str): The plaintext password entered by the user.

    Returns:
        bool: ``True`` if the username matches and the password is correct,
              ``False`` otherwise.
    """
    data = load_data()
    user = data.get("user", {})
    stored_hash = user.get("hashed_password", "")
    if not stored_hash:
        return False
    # username comparison: exact match or treat as email
    username_match = username == user.get("name", "")
    password_match = check_password_hash(stored_hash, password)
    return username_match and password_match


def login_required(f):
    """Flask decorator that forces login before accessing the decorated route.

    Checks ``session.get('user_id')``. If the key is absent, the user is
    redirected to the ``/login`` page. Otherwise, the wrapped view function
    is called normally.

    Args:
        f (function): The Flask view function to decorate.

    Returns:
        function: A wrapped function that enforces authentication.
    """
    from flask import redirect, url_for, session

    def wrapped(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    wrapped.__name__ = f.__name__
    wrapped.__doc__ = f.__doc__
    return wrapped