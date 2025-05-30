import logging
import re
from typing import Tuple, Optional

def create_logger(name: str, log_file: str = None) -> logging.Logger:
    """
    Create a logger with the specified name and optional log file.
    
    Args:
        name: The name of the logger.
        log_file: Optional file to write logs to.
    
    Returns:
        A configured Logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Create console handler if not already present
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # Create file handler if log_file is provided and not already present
    if log_file and not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

def check_galaxy_mention(text: str, logger: logging.Logger) -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Check if the text contains a galaxy mention and extract its name and ID if possible.
    
    Args:
        text: The text to check for galaxy mention.
        logger: Logger instance for debugging.
    
    Returns:
        Tuple of (is_galaxy, galaxy_name, galaxy_id).
        - is_galaxy: True if text likely refers to a galaxy.
        - galaxy_name: The name of the galaxy if recognized, None otherwise.
        - galaxy_id: The ID of the galaxy if recognized or parsed, None otherwise.
    """
    logger.debug(f"Checking galaxy mention in text: {text}")
    text_lower = text.lower()
    
    # Simple check for galaxy number
    match = re.search(r'galaxy\s+(\d+)', text_lower)
    if match:
        gal_id = int(match.group(1))
        if 1 <= gal_id <= 256:
            logger.debug(f"Matched galaxy ID: {gal_id}")
            return True, f"Galaxy {gal_id}", gal_id
    
    # Check for known galaxy names (partial list)
    known_galaxies = {
        "euclid": 1,
        "hilbert dimension": 2,
        "calypso": 3,
        "hesperius dimension": 4,
        "hyades": 5,
        "i've lost count": 256  # Example placeholder
    }
    
    for name, gal_id in known_galaxies.items():
        if name in text_lower:
            logger.debug(f"Matched galaxy name: {name} (ID: {gal_id})")
            return True, name.capitalize(), gal_id
    
    logger.debug("No galaxy mention found")
    return False, None, None
