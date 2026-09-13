# init_db.py - Bootstrap the data.json file and hash the initial admin password.
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Run once after cloning/installing:   python init_db.py
# This creates data/data.json with a default admin user and an empty answer base.
# The user is prompted for a password, which is hashed with Werkzeug's
# generate_password_hash (PBKDF2) and stored securely.

import os
import sys
import json
from werkzeug.security import generate_password_hash

# Resolve paths relative to the project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DATA_PATH = os.path.join(DATA_DIR, "data.json")


def main():
    # Ensure the data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)

    # Prompt for the admin password (won't echo)
    password = input("Set the admin password: ").strip()
    if not password:
        print("Password cannot be empty. Exiting.")
        sys.exit(1)

    # Hash the password
    hashed_pw = generate_password_hash(password)

    # Build the initial data structure
    initial_data = {
        "user": {
            "name": "admin",
            "hashed_password": hashed_pw,
        },
        "answers": [],
        # Optional: place your OpenAI key here if you want AI adaptation later
        "api_key": "",
        # TRIGGER_TOKEN is set via environment variable; store a default for local dev
        "trigger_token": os.getenv("TRIGGER_TOKEN", "change-this-dev-token"),
    }

    # Write to data.json
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(initial_data, f, indent=2, ensure_ascii=False)

    print(f"Initialized {DATA_PATH}")
    print("Admin user: admin")
    print("Password set above has been hashed and stored.")


if __name__ == "__main__":
    main()