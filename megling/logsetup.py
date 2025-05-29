import logging
from logging.handlers import RotatingFileHandler

def setupLogger(name:str="megling"):
  # Logger
  logger = logging.getLogger(name)
  logger.setLevel(logging.INFO)
  # logger = logging.getLogger(__name__) to access

  if not logger.handlers:
    # Console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # File
    file_handler = RotatingFileHandler( "logs/bot.log", maxBytes=1_000_000, backupCount=5, encoding='utf-8' )
    file_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

  return logger
