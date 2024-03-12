import logging
import os
from .version import __version__

repo_root = os.path.abspath(os.path.join(__file__, os.pardir, os.pardir))


class Logger:
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.level, line.rstrip())


def logger_name_from_filepath(filepath):
    relative_path = os.path.relpath(filepath, start=repo_root)
    return (
        relative_path.
        replace('/', '.').
        replace('.py', '')
    )


def get_error_logger():
    return Logger(logging.getLogger(), logging.ERROR)


def get_logger(filepath=None):
    if filepath:
        logger = logging.getLogger(
            logger_name_from_filepath(filepath)
        )
    else:
        logger = logging.getLogger()

    logger.setLevel(logging.DEBUG)
    return logger
