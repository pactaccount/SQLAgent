"""Project-relative configuration for the API, database and model gateway."""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)
DATA = Path(os.getenv("SQLAGENT_DATA_DIR", ROOT / "artifacts" / "runtime")).resolve()
QUERY_SECONDS = float(os.getenv("SQLAGENT_QUERY_SECONDS", "10"))
