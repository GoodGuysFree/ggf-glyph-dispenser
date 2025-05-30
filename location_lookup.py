from fuzzywuzzy import fuzz, process
import json
import os
import shutil
from typing import Dict, Optional, List, Union

DEFAULT_LOCATIONS_FILE = "locations.json"

def load_locations(filename: str = DEFAULT_LOCATIONS_FILE, logger=None) -> Dict:
    """Load locations from file or return empty dict if file doesn't exist."""
    if logger:
        logger.debug(f"Loading locations from {filename}")
    try:
        with open(filename, 'r') as f:
            locations = json.load(f)
        if logger:
            logger.debug(f"Loaded {len(locations)} locations")
        return locations
    except FileNotFoundError:
        if logger:
            logger.warning(f"Locations file not found: {filename}")
        return {}
    except json.JSONDecodeError as e:
        if logger:
            logger.error(f"Invalid JSON in {filename}: {str(e)}")
        return {}

def save_locations(locations: Dict, filename: str = DEFAULT_LOCATIONS_FILE, logger=None) -> None:
    """Safely save locations to file using temp file and atomic rename."""
    if logger:
        logger.debug(f"Saving {len(locations)} locations to {filename}")
    temp_file = filename + ".tmp"
    backup_file = filename + ".bak"
    
    try:
        with open(temp_file, 'w') as f:
            json.dump(locations, f, indent=4)
        
        if os.path.exists(filename):
            shutil.move(filename, backup_file)
            if logger:
                logger.debug(f"Backed up {filename} to {backup_file}")
        os.rename(temp_file, filename)
        if logger:
            logger.debug(f"Renamed {temp_file} to {filename}")
        if os.path.exists(backup_file):
            os.remove(backup_file)
            if logger:
                logger.debug(f"Removed backup file {backup_file}")
    except Exception as e:
        if logger:
            logger.error(f"Failed to save locations to {filename}: {str(e)}")
        raise

def find_location_in_string(input_string: str, threshold: int = 80, filename: str = DEFAULT_LOCATIONS_FILE, logger=None) -> Optional[Dict]:
    """
    Search for a known location in the input string using both fuzzy matching and substring search,
    updating counter if found. Uses substring matches when they yield 1-2 results.
    """
    if logger:
        logger.debug(f"Searching for location in string: {input_string}")
    if not input_string or not isinstance(input_string, str):
        if logger:
            logger.warning("Invalid input string: empty or not a string")
        return None
        
    locations = load_locations(filename, logger)
    input_lower = input_string.lower()
    location_names = list(locations.keys())
    
    # First try substring matching - check if input contains any location name or its words
    substring_matches = []
    for name in location_names:
        name_lower = name.lower()
        # Check if the full name or any individual word from the name appears in input
        if input_lower in name_lower:
            substring_matches.append(name)
    
    if 1 <= len(substring_matches) <= 2:
        # If we have 1-2 substring matches, use the first one
        match_name = substring_matches[0]
        locations[match_name]["num_returns"] += 1
        save_locations(locations, filename, logger)
        if logger:
            logger.info(f"Found location via substring match: {match_name}")
        return locations[match_name]
    
    # If substring didn't give us a small set of matches, fall back to fuzzy matching
    # Try full phrase matching
    best_match = process.extractOne(
        input_lower,
        location_names,
        scorer=fuzz.partial_ratio
    )
    
    if best_match and best_match[1] >= threshold:
        match_name = best_match[0]
        match_lower = match_name.lower()
        if (match_lower in input_lower or 
            any(fuzz.ratio(word, match_lower) >= threshold 
                for word in input_lower.split())):
            locations[match_name]["num_returns"] += 1
            save_locations(locations, filename, logger)
            if logger:
                logger.info(f"Found location via fuzzy match: {match_name}, score={best_match[1]}")
            return locations[match_name]
    
    # Try single-word matching
    input_words = input_lower.split()
    for word in input_words:
        matches = []
        for loc_name in location_names:
            loc_words = loc_name.split()
            for loc_word in loc_words:
                if fuzz.ratio(word, loc_word) >= threshold:
                    matches.append(loc_name)
        
        if len(matches) == 1:
            locations[matches[0]]["num_returns"] += 1
            save_locations(locations, filename, logger)
            if logger:
                logger.info(f"Found location via single-word match: {matches[0]}")
            return locations[matches[0]]
    
    if logger:
        logger.debug("No location found in string")
    return None

def register_location(name: str, galaxy: str, address: str, description: str = "No description provided", filename: str = DEFAULT_LOCATIONS_FILE, logger=None) -> bool:
    """Register a new location."""
    if logger:
        logger.debug(f"Attempting to register location: {name}, galaxy={galaxy}, address={address}")
    locations = load_locations(filename, logger)
    if name.lower() in [n.lower() for n in locations.keys()] or f"{galaxy}-{address}".lower() in [f"{i['galaxy']}-{i['address']}".lower() for i in locations.values()]:
        if logger:
            logger.warning(f"Location registration failed: duplicate name {name} or galaxy-address {galaxy}-{address}")
        return False
    
    locations[name] = {
        "galaxy": galaxy,
        "address": address,
        "num_returns": 0,
        "description": description
    }
    save_locations(locations, filename, logger)
    if logger:
        logger.info(f"Successfully registered location: {name}")
    return True

def list_top_locations(num: Union[str, int], filename: str = DEFAULT_LOCATIONS_FILE, logger=None) -> List[Dict]:
    """Return the top N most returned locations."""
    try:
        n = int(num)
    except (ValueError, TypeError):
        n = 0
        if logger:
            logger.warning(f"Invalid number for top locations: {num}, defaulting to 0")
        
    locations = load_locations(filename, logger)
    if logger:
        logger.debug(f"Listing top {n} locations")
    sorted_locs = sorted(
        locations.items(),
        key=lambda x: x[1]["num_returns"],
        reverse=True
    )
    result = [dict(name=name, **data) for name, data in sorted_locs[:n]]
    if logger:
        logger.debug(f"Returning {len(result)} top locations")
    return result

def modify_location(name: str, old_galaxy: str, old_address: str, 
                   new_galaxy: Optional[str] = None, 
                   new_address: Optional[str] = None,
                   new_description: Optional[str] = None,
                   filename: str = DEFAULT_LOCATIONS_FILE, logger=None) -> bool:
    """Modify an existing location's details if it matches the old values."""
    if logger:
        logger.debug(f"Attempting to modify location: {name}, old_galaxy={old_galaxy}, old_address={old_address}")
    locations = load_locations(filename, logger)
    name_lower = name.lower()
    
    if name_lower not in locations:
        if logger:
            logger.warning(f"Location not found: {name}")
        return False
    
    loc = locations[name_lower]
    if loc["galaxy"] != old_galaxy or loc["address"] != old_address:
        if logger:
            logger.warning(f"Location {name} does not match old values: galaxy={loc['galaxy']}, address={loc['address']}")
        return False
    
    if new_galaxy is not None:
        loc["galaxy"] = new_galaxy
    if new_address is not None:
        loc["address"] = new_address
    if new_description is not None:
        loc["description"] = new_description
        
    if new_galaxy is not None or new_address is not None or new_description is not None:
        save_locations(locations, filename, logger)
        if logger:
            logger.info(f"Successfully modified location: {name}")
    return True

def format_locations_list(locations: List[Dict]) -> str:
    """
    Format a list of location dictionaries into a nicely readable string.
    """
    if not locations:
        return "No locations to display."
        
    max_name = max(len(loc["name"]) for loc in locations)
    max_galaxy = 6
    max_address = 12
    max_returns = 7
    
    header = (
        f"{'Name':<{max_name}}  {'Galaxy':<{max_galaxy}}  "
        f"{'Address':<{max_address}}  {'Returns':<{max_returns}}  Description\n"
    )
    separator = "-" * (max_name + max_galaxy + max_address + max_returns + 20) + "\n"
    
    rows = []
    for loc in locations:
        row = (
            f"{loc['name']:<{max_name}}  {loc['galaxy']:<{max_galaxy}}  "
            f"{loc['address']:<{max_address}}  {loc['num_returns']:<{max_returns}}  "
            f"{loc['description']}"
        )
        rows.append(row)
    
    return header + separator + "\n".join(rows)

if __name__ == "__main__":
    from logger import create_logger
    logger = create_logger(script_name="location_lookup", log_file="test.log")
    test_strings = [
        "I'm going to New Aleria tomorrow",
        "nEw aLeRiA is awesome",
        "crystal falls is beautiful",
        "crystol fals looks nice",
        "nothing here",
        "edenprime",
        "SHADOW REALM TIME",
    ]
    
    for test in test_strings:
        result = find_location_in_string(test, logger=logger)
        logger.info(f"Input: {test}")
        logger.info(f"Result: {result}")
    
    register_location("test planet", "5", "123456789ABC", "A test world", logger=logger)
    logger.info(f"Top 3 locations: {list_top_locations(3, logger=logger)}")
    modify_location("test planet", "5", "123456789ABC", new_description="Modified test world", logger=logger)
    logger.info(f"Top 5 locations: {list_top_locations('5', logger=logger)}")
    logger.info(f"Top with invalid input: {list_top_locations('invalid', logger=logger)}")

    logger.debug(f"Current working directory: {os.getcwd()}")
    logger.info(f"Find 'cyc': {find_location_in_string('cyc', logger=logger)}")