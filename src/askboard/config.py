"""Settings, read from environment variables."""

import os

# Which storage to use: "memory" or "sqlite".
STORAGE = os.environ.get("ASKBOARD_STORAGE", "memory")

# Path of the SQLite database file, used when STORAGE is "sqlite".
DB_PATH = os.environ.get("ASKBOARD_DB", "askboard.db")

# Logging in with this password gives the "speaker" role (mark answered, delete).
SPEAKER_PASSWORD = os.environ.get("ASKBOARD_SPEAKER_PASSWORD", "speaker")

# Rate limit for writes (asking and voting): at most RATE_LIMIT requests per
# user every RATE_WINDOW seconds.
RATE_LIMIT = int(os.environ.get("ASKBOARD_RATE_LIMIT", "10"))
RATE_WINDOW = float(os.environ.get("ASKBOARD_RATE_WINDOW", "10"))
