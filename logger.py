# logger.py

import logging
from datetime import datetime
from pathlib import Path
from config import LOG_DIR

def setup_logger(name: str = "token_manager") -> logging.Logger:
    log_dir = Path(LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    session_log_file = log_dir / f"session_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File
    file_handler = logging.FileHandler(session_log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.info(f"Logger initialisé pour la session : {session_log_file.name}")
    return logger

# Logger global (à importer dans chaque module)
logger = setup_logger()