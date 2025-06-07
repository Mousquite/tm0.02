# config.py

from pathlib import Path

# === CHEMINS PAR DÉFAUT ===
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
LOG_DIR = BASE_DIR / "logs"

DEFAULT_DB_FILE = DATA_DIR / "token_data.xlsx"
IMPORT_FILE = DATA_DIR / "import.xlsx"
EXPORT_FILE = EXPORT_DIR / "export.xlsx"

# === COLONNES IMMUTABLES ===
IMMUTABLE_COLUMNS = ["contract_address", "token_id", "chain"]

# === CONFIG TABLE ===
CHECKBOX_COLUMN = "✔️"
LOCKED_CELL_STYLE = "font-weight: bold;"
MODIFIED_CELL_COLOR = "#FFFACD"  # light yellow

# === UI ===
WINDOW_TITLE = "Token Manager"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 800

# === DIVERS ===
MAX_UNDO_STACK = 100