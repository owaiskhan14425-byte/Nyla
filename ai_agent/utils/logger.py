import os
import logging
import sys
import json

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

file_handler = logging.FileHandler(os.path.join(LOG_DIR, "error.log"),encoding='utf-8')
file_handler.setLevel(logging.ERROR)
file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(file_formatter)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.ERROR)
stream_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
stream_handler.setFormatter(stream_formatter)

logger = logging.getLogger()
logger.setLevel(logging.ERROR)
logger.handlers.clear()
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

def log_error(msg, exc_info=True):
    logger.error(msg, exc_info=exc_info)
    
    
    

#for add conversation data 

data_file_handler = logging.FileHandler(os.path.join(LOG_DIR, "rag.log"),encoding='utf-8')
data_file_handler.setLevel(logging.INFO)
data_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
data_file_handler.setFormatter(data_formatter)

data_logger = logging.getLogger("data_logger")
data_logger.setLevel(logging.INFO)
data_logger.handlers.clear()
data_logger.addHandler(data_file_handler)

def log_data_dict(data: dict):
    data_logger.info(json.dumps(data, ensure_ascii=False))
