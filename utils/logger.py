import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime

def setup_logging():
    """Setup application logging configuration"""
    
    # Create logs directory if it doesn't exist
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure root logger
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler for general application logs
    app_file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'application.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    app_file_handler.setLevel(logging.INFO)
    app_file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(app_file_handler)
    
    # File handler for deployment logs
    deployment_file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'deployments.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=10
    )
    deployment_file_handler.setLevel(logging.INFO)
    deployment_file_handler.setFormatter(detailed_formatter)
    
    # Add deployment handler to specific loggers
    deployment_loggers = [
        'services.deployment_manager',
        'services.harness_client',
        'services.k8s_client',
        'services.yaml_processor'
    ]
    
    for logger_name in deployment_loggers:
        logger = logging.getLogger(logger_name)
        logger.addHandler(deployment_file_handler)
    
    # Error file handler
    error_file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'errors.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(error_file_handler)
    
    # Suppress some noisy loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('kubernetes').setLevel(logging.WARNING)
    
    logging.info("Logging configuration initialized")

def get_deployment_logger(deployment_id: str):
    """Get a logger specific to a deployment"""
    logger_name = f"deployment.{deployment_id}"
    logger = logging.getLogger(logger_name)
    
    if not logger.handlers:
        # Create deployment-specific log file
        log_dir = 'logs/deployments'
        os.makedirs(log_dir, exist_ok=True)
        
        handler = logging.FileHandler(
            os.path.join(log_dir, f"{deployment_id}.log")
        )
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return logger

class DeploymentLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds deployment context to log messages"""
    
    def __init__(self, logger, deployment_id, batch_id=None):
        self.deployment_id = deployment_id
        self.batch_id = batch_id
        super().__init__(logger, {})
    
    def process(self, msg, kwargs):
        context = f"[Deployment:{self.deployment_id}"
        if self.batch_id:
            context += f", Batch:{self.batch_id}"
        context += "]"
        return f"{context} {msg}", kwargs

def setup_request_logging():
    """Setup request logging for Flask"""
    import flask
    
    @flask.Flask.before_request
    def log_request_info():
        logger = logging.getLogger('flask.request')
        logger.info(f"{flask.request.method} {flask.request.url} - {flask.request.remote_addr}")
    
    @flask.Flask.after_request
    def log_request_response(response):
        logger = logging.getLogger('flask.request')
        logger.info(f"Response: {response.status_code}")
        return response
