import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from core.config import Config


class CustomLogger:
    def __init__(self, name=None, log_dir=None, log_level=None):
        self.name = name or 'crypto_bot'
        self.log_dir = log_dir or 'logs'
        self.log_level = getattr(logging, log_level or Config.LOG_LEVEL)

        # Create logs directory
        os.makedirs(self.log_dir, exist_ok=True)

        # Setup logger
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(self.log_level)

        # Clear existing handlers
        self.logger.handlers = []

        # Add handlers
        self._add_console_handler()
        self._add_file_handler()
        self._add_error_handler()

    def _add_console_handler(self):
        """Add console handler"""
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level)

        # Format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)

        self.logger.addHandler(console_handler)

    def _add_file_handler(self):
        """Add rotating file handler for all logs"""
        log_file = os.path.join(self.log_dir, 'trading_bot.log')

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(self.log_level)

        # Format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)

    def _add_error_handler(self):
        """Add separate file handler for errors only"""
        error_file = os.path.join(self.log_dir, 'errors.log')

        error_handler = TimedRotatingFileHandler(
            error_file,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.suffix = "%Y%m%d"

        # Format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        error_handler.setFormatter(formatter)

        self.logger.addHandler(error_handler)

    def get_logger(self):
        """Get logger instance"""
        return self.logger

    def debug(self, msg):
        self.logger.debug(msg)

    def info(self, msg):
        self.logger.info(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def error(self, msg):
        self.logger.error(msg)

    def critical(self, msg):
        self.logger.critical(msg)

    def exception(self, msg):
        self.logger.exception(msg)


# Create default logger instance
logger = CustomLogger().get_logger()
