"""
Custom logging formatters for HotCalls project.
"""
import logging
import json


class DetailedFormatter(logging.Formatter):
    """
    Custom formatter that includes extra fields from structured logging.
    
    This formatter displays additional context information passed via the 'extra' 
    parameter in logging calls, which is crucial for debugging Meta lead processing.
    """
    
    def format(self, record):
        # Start with the standard formatted message
        formatted = super().format(record)
        
        # Extract extra fields that were passed to the logging call
        extra_fields = {}
        
        # Standard fields that should not be included in extra
        standard_fields = {
            'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
            'module', 'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
            'thread', 'threadName', 'processName', 'process', 'getMessage',
            'exc_info', 'exc_text', 'stack_info', 'asctime', 'message'
        }
        
        # Collect all extra fields from the log record
        for key, value in record.__dict__.items():
            if key not in standard_fields:
                extra_fields[key] = value
        
        # If there are extra fields, append them to the log message
        if extra_fields:
            try:
                extra_str = json.dumps(extra_fields, default=str, sort_keys=True)
                formatted += f" | EXTRA: {extra_str}"
            except (TypeError, ValueError):
                # Fallback to simple string representation if JSON fails
                extra_str = ", ".join(f"{k}={v}" for k, v in extra_fields.items())
                formatted += f" | EXTRA: {extra_str}"
        
        return formatted