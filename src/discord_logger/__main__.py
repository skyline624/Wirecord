'''Entry point for Discord Logger.

This module serves as the entry point when running the package
as a module: python -m discord_logger
'''
import sys

from discord_logger.interfaces.cli import main

if __name__ == '__main__':
    sys.exit(main())
