from __future__ import annotations

import logging

__all__ = [
    'logger',
]

logger = logging.getLogger(str(__package__).split('.')[0])
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('[%(name)s] %(levelname)s: %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)
