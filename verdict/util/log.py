import os
import sys
from typing import Optional

from loguru import logger as base_logger

from verdict import config

# logging
VERDICT_COMPACT_LOG_FORMAT: str = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <red>{extra[unit]: >80} T={extra[thread_id]: <5}</red> | <cyan>{function}</cyan> - <level>{message:.150}...</level>"
VERDICT_VERBOSE_LOG_FORMAT: str = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <red>{extra[unit]: >80} T={extra[thread_id]: <5}</red> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"

logger = base_logger.bind(thread_id="main", unit="")
logger.remove()


def init_logger(name: Optional[str] = None) -> None:
    global logger
    logger.remove()
    logger.add(sys.stderr, format=VERDICT_COMPACT_LOG_FORMAT, level="CRITICAL")

    if config.DEBUG or (log_level := os.getenv("LOG_LEVEL", False)):
        logger.add(
            sys.stderr, format=VERDICT_COMPACT_LOG_FORMAT, level=log_level or "DEBUG"
        )

    if name and not os.getenv("VERDICT_NO_LOG", False):
        logger.add(
            config.VERDICT_LOG_DIR / f"{name}_{{time}}.log",
            format=VERDICT_VERBOSE_LOG_FORMAT,
        )
