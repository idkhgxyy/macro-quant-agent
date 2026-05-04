import logging
from logging.handlers import RotatingFileHandler
import os
import sys

def setup_logger(name="QuantAgent"):
    """
    配置并返回一个标准化的 logger。
    同时输出到控制台（标准输出）和本地日志文件。
    """
    logger = logging.getLogger(name)
    
    # 避免重复绑定 handler
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)
    
    # 格式化器
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 1. 控制台 Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 2. 文件 Handler (按需写入本地文件，方便审计留痕)
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    max_bytes = int(os.getenv("LOG_MAX_BYTES", "5000000"))
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "trading_system.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger
