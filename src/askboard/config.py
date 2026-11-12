"""Settings, read from environment variables."""

import os

# Which storage to use: "memory" or "sqlite".
STORAGE = os.environ.get("ASKBOARD_STORAGE", "memory")

# Path of the SQLite database file, used when STORAGE is "sqlite".
DB_PATH = os.environ.get("ASKBOARD_DB", "askboard.db")
