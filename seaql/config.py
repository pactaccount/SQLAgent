"""Project-relative configuration for the API, database and model gateway."""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)
DATA = Path(os.getenv("SQLAGENT_DATA_DIR", ROOT / "artifacts" / "runtime")).resolve()
MAX_ROWS = int(os.getenv("SQLAGENT_MAX_ROWS", "1000"))
QUERY_SECONDS = float(os.getenv("SQLAGENT_QUERY_SECONDS", "10"))
UPLOAD_BYTES = int(os.getenv("SQLAGENT_UPLOAD_MB", "150")) * 1024 * 1024
