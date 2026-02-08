"""Central logging configuration."""

import logging


def configure_logging(level: str = 'INFO'):
    lvl = getattr(logging, level.upper(), logging.INFO)
    fmt = '%(asctime)s %(levelname)s %(name)s: %(message)s'
    logging.basicConfig(level=lvl, format=fmt)
