'''CLI interface for Discord Logger.

This module provides the command-line interface for the Discord Logger,
handling argument parsing, signal management, and application startup.
'''
import argparse
import logging
import signal
import sys
from pathlib import Path
from typing import List, Optional

from discord_logger.config import DiscordLoggerConfig


logger = logging.getLogger(__name__)


class SignalHandler:
    '''Handler for graceful shutdown on SIGINT.
    
    Attributes:
        _interrupted: Flag indicating if shutdown was requested.
    '''
    
    def __init__(self) -> None:
        '''Initialize the signal handler.'''
        self._interrupted = False
    
    def handle(self, signum: int, frame: Optional[object]) -> None:
        '''Handle SIGINT signal.
        
        Args:
            signum: Signal number received.
            frame: Current stack frame.
        '''
        logger.info('Received SIGINT, shutting down gracefully...')
        self._interrupted = True
    
    @property
    def interrupted(self) -> bool:
        '''Check if shutdown was requested.'''
        return self._interrupted
    
    def register(self) -> None:
        '''Register the signal handler for SIGINT.'''
        signal.signal(signal.SIGINT, self.handle)


def create_argument_parser() -> argparse.ArgumentParser:
    '''Create the argument parser for CLI.
    
    Returns:
        Configured ArgumentParser instance.
    '''
    parser = argparse.ArgumentParser(
        prog='discord-logger',
        description='Capture et export de traffic Discord Gateway',
        epilog='Example: python -m discord_logger 123456789 987654321'
    )
    
    parser.add_argument(
        'channel_ids',
        metavar='CHANNEL_ID',
        nargs='*',
        help='Discord channel IDs to monitor (positional arguments)'
    )
    
    parser.add_argument(
        '--log-dir',
        type=Path,
        default=Path('logs'),
        help='Directory for log files (default: logs)'
    )
    
    parser.add_argument(
        '--archive-dir',
        type=Path,
        default=Path('traffic_archive'),
        help='Directory for archived capture files (default: traffic_archive)'
    )
    
    parser.add_argument(
        '--persistence-file',
        type=Path,
        default=Path('.persistence'),
        help='File for persistence data (default: .persistence)'
    )
    
    parser.add_argument(
        '--scan-interval',
        type=int,
        default=5,
        help='Interval in seconds between directory scans (default: 5)'
    )
    
    parser.add_argument(
        '--save-interval',
        type=int,
        default=30,
        help='Interval in seconds between persistence saves (default: 30)'
    )
    
    parser.add_argument(
        '--max-keys',
        type=int,
        default=10000,
        help='Maximum number of deduplication keys to store (default: 10000)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 1.0.0'
    )
    
    return parser


def print_startup_message(config: DiscordLoggerConfig) -> None:
    '''Print startup message with configuration.
    
    Args:
        config: Configuration instance to display.
    '''
    print()
    print('=' * 60)
    print('  Discord Logger - Capture Gateway')
    print('=' * 60)
    print(f'  Log directory:      {config.log_dir}')
    print(f'  Archive directory:  {config.archive_dir}')
    print(f'  Persistence file:   {config.persistence_file}')
    print(f'  Channel IDs:        {config.channel_ids or "(all)"}')
    print(f'  Scan interval:      {config.scan_interval}s')
    print(f'  Save interval:      {config.save_interval}s')
    print(f'  Max keys:           {config.max_keys}')
    print('=' * 60)
    print()
    logger.info('Discord Logger started')


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    '''Parse command-line arguments.
    
    Args:
        args: Optional list of arguments to parse.
        
    Returns:
        Parsed arguments namespace.
    '''
    parser = create_argument_parser()
    return parser.parse_args(args)


def create_config_from_args(args: argparse.Namespace) -> DiscordLoggerConfig:
    '''Create configuration from parsed arguments.
    
    Args:
        args: Parsed arguments namespace.
        
    Returns:
        Configured DiscordLoggerConfig instance.
    '''
    # Start with environment config as base
    config = DiscordLoggerConfig.from_env()
    
    # Override with CLI arguments
    config.log_dir = args.log_dir
    config.archive_dir = args.archive_dir
    config.persistence_file = args.persistence_file
    config.scan_interval = args.scan_interval
    config.save_interval = args.save_interval
    config.max_keys = args.max_keys
    
    # Channel IDs from positional arguments override env
    if args.channel_ids:
        config.channel_ids = list(args.channel_ids)
    
    return config


def setup_logging(verbose: bool = False) -> None:
    '''Setup logging configuration.
    
    Args:
        verbose: Enable verbose logging if True.
    '''
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main(args: Optional[List[str]] = None) -> int:
    '''Main entry point for CLI.
    
    Args:
        args: Optional list of arguments to parse.
        
    Returns:
        Exit code (0 for success, non-zero for errors).
    '''
    parsed_args = parse_args(args)
    
    setup_logging(parsed_args.verbose)
    
    # Setup signal handler for graceful shutdown
    signal_handler = SignalHandler()
    signal_handler.register()
    
    # Create configuration
    config = create_config_from_args(parsed_args)
    config.ensure_directories()
    
    # Print startup message
    print_startup_message(config)
    
    logger.info(f'Monitoring channels: {config.channel_ids or "all"}')
    
    # Main loop - would integrate with the actual capture service here
    try:
        while not signal_handler.interrupted:
            # Placeholder for actual capture logic
            import time
            time.sleep(config.scan_interval)
    except KeyboardInterrupt:
        pass
    finally:
        logger.info('Discord Logger stopped')
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
