"""GoldAI Ultra — Logger"""
import logging
import sys
from pathlib import Path

try:
    from colorlog import ColoredFormatter
    _HAS_COLOR = True
except ImportError:
    _HAS_COLOR = False


def _setup() -> logging.Logger:
    log = logging.getLogger("goldai")
    if log.handlers:
        return log
    log.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    if _HAS_COLOR:
        ch.setFormatter(ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)-8s]%(reset)s %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG": "cyan", "INFO": "green", "WARNING": "yellow",
                "ERROR": "red", "CRITICAL": "bold_red,bg_white"
            }
        ))
    else:
        ch.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(message)s", datefmt="%H:%M:%S"
        ))
    log.addHandler(ch)

    # File handler
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        fh = logging.FileHandler(log_dir / "goldai_ultra.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        log.addHandler(fh)
    except Exception:
        pass

    return log


logger = _setup()
