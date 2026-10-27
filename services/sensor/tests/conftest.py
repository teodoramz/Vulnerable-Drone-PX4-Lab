import os
import pathlib

# Configure settings before anything imports app.main. EVE_PATH does not exist
# and C2_URL is unreachable, so pushes fail fast.
_TMP_EVE = pathlib.Path(__file__).parent / "_no_such_eve.json"

os.environ.setdefault("EVE_PATH", str(_TMP_EVE))
os.environ.setdefault("EVE_POLL_INTERVAL", "0.05")
os.environ.setdefault("C2_URL", "http://127.0.0.1:1")  # nothing listens here
os.environ.setdefault("IDS_PUSH_TOKEN", "test-token")
os.environ.setdefault("PUSH_MAX_RETRIES", "1")
os.environ.setdefault("PUSH_BASE_DELAY", "0.01")
os.environ.setdefault("PUSH_MAX_DELAY", "0.01")
os.environ.setdefault("PUSH_TIMEOUT", "0.2")
os.environ.setdefault("ALERT_BUFFER_SIZE", "2000")
