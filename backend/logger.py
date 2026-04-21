import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from config import get_settings

settings = get_settings()

# Ensure logs directory exists
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOG_FILE = LOGS_DIR / "server.log"

def setup_logging():
    """Configures global logging for the application."""
    log_level = logging.DEBUG if settings.is_development else logging.INFO
    
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Format for logs
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 1. Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 2. Rotating File Handler (5MB per file, max 5 backups)
    file_handler = RotatingFileHandler(
        LOG_FILE, 
        maxBytes=5 * 1024 * 1024, 
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    logging.info(f"Logging initialized. Mode: {'Development' if settings.is_development else 'Production'}")
    logging.info(f"Log file: {LOG_FILE}")

def get_logger(name: str):
    """Utility to get a named logger."""
    return logging.getLogger(name)
