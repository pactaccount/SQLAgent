"""Explicit configuration shared by the API, model gateway and launcher."""
import os
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env', override=False)
DATA = Path(os.getenv('SQLAGENT_DATA_DIR', ROOT / 'artifacts' / 'runtime')).resolve()
MODEL_PATH = ROOT / 'models' / 'qwen2.5-coder-7b-instruct-4bit'
MODEL_URL = os.getenv('SQLAGENT_MODEL_URL', 'http://127.0.0.1:8081').rstrip('/')
MAX_ROWS = int(os.getenv('SQLAGENT_MAX_ROWS', '1000'))
QUERY_SECONDS = float(os.getenv('SQLAGENT_QUERY_SECONDS', '10'))
UPLOAD_BYTES = int(os.getenv('SQLAGENT_UPLOAD_MB', '150')) * 1024 * 1024
