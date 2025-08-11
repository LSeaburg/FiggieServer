from datetime import datetime
import logging

def format_timestamp(timestamp_str: str) -> str:
    """Format ISO timestamp string to human-readable format"""
    if not timestamp_str:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime("%B %d, %Y at %I:%M %p")
    except (ValueError, AttributeError):
        logging.getLogger(__name__).debug("Failed to parse timestamp: %s", timestamp_str)
        return timestamp_str
