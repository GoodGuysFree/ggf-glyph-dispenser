#https://discord.com/oauth2/authorize?client_id=1353661339968475136&permissions=2147601472&integration_type=0&scope=bot+applications.commands
import discord
from discord import app_commands, ui
from fuzzywuzzy import fuzz
import json
from typing import Dict, List, Optional
from ggf_bot_utils import check_galaxy_mention, create_logger
from pathlib import Path

# Set up logger
script_name = Path(__file__).stem
logger = create_logger(script_name, log_file='glyph-dispenser-bot.log')

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

PRIVILEGED_ROLE_ID = 1319567365200937002
DEFAULT_LOCATIONS_FILE = "locations.json"

# Channel to filename mapping
CHANNEL_FILE_MAPPING = {
    1340078285731790878: "bytebeat-arena-locations.json", # bytebeat-arena
    # 987654321098765432: "channel2_locations.json",
    # Add more channel IDs and corresponding filenames as needed
}

USE_EPHEMERAL = False

from location_lookup import (
    load_locations, save_locations, find_location_in_string,
    register_location, list_top_locations, modify_location, format_locations_list
)

def validate_address(address: str) -> bool:
    """Validate if address is a 12-digit hex number with first digit 1-6."""
    logger.debug(f"Validating address: {address}")
    if len(address) != 12 or not all(c in '0123456789ABCDEFabcdef' for c in address):
        logger.warning(f"Invalid address format: {address}")
        return False
    if address[0] not in '123456':
        logger.warning(f"Address first digit not in 1-6: {address}")
        return False
    return True

def parse_glyph_url(url: str) -> Optional[tuple]:
    """Parse galaxy and address from URL format."""
    logger.debug(f"Parsing glyph URL: {url}")
    if not url.startswith("https://glyphs.had.sh/"):
        logger.warning(f"URL does not start with glyphs.had.sh: {url}")
        return None
    parts = url.replace("https://glyphs.had.sh/", "").split("_")
    if len(parts) != 2:
        logger.warning(f"Invalid URL format, expected 2 parts: {url}")
        return None
    if not validate_address(parts[1]):
        logger.warning(f"Invalid address in URL: {parts[1]}")
        return None
    is_gal, _, gal_id = check_galaxy_mention(f"galaxy {parts[0]}", logger)
    if not is_gal:
        logger.warning(f"Invalid galaxy in URL: {parts[0]}")
        return None
    logger.debug(f"Parsed URL: galaxy={gal_id}, address={parts[1]}")
    return (str(gal_id), parts[1])

def find_location_by_galaxy_address(galaxy: str, address: str, filename: str = DEFAULT_LOCATIONS_FILE) -> Optional[Dict]:
    """Find location by exact galaxy and address match."""
    logger.debug(f"Searching for location: galaxy={galaxy}, address={address}, file={filename}")
    locations = load_locations(filename, logger)
    for loc_data in locations.values():
        if loc_data["galaxy"] == galaxy and loc_data["address"] == address:
            logger.debug(f"Found matching location: {loc_data}")
            return loc_data
    logger.debug("No matching location found")
    return None

def get_channel_filename(channel_id: int) -> str:
    """Get the appropriate filename based on channel ID."""
    filename = CHANNEL_FILE_MAPPING.get(channel_id, DEFAULT_LOCATIONS_FILE)
    logger.debug(f"Resolved channel {channel_id} to filename: {filename}")
    return filename

# Modal definitions
class AddModal(ui.Modal, title="Add New Location"):
    name = ui.TextInput(label="Name", placeholder="e.g., Crystal Falls", required=True)
    galaxy = ui.TextInput(label="Galaxy (1-256 or name)", placeholder="e.g., 2 or Euclid", required=True)
    address = ui.TextInput(label="Address (12-digit hex, 1-6 first)", placeholder="e.g., 1A2B3C4D5E6F", required=True)
    description = ui.TextInput(label="Description (optional)", placeholder="e.g., A new colony", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        filename = get_channel_filename(interaction.channel_id)
        name = self.name.value
        galaxy_input = self.galaxy.value
        address = self.address.value.upper()
        description = self.description.value or "No description provided"

        logger.info(f"AddModal: Processing name={name}, galaxy={galaxy_input}, address={address}, description={description}, file={filename}")
        galaxy_check_input = f"galaxy {galaxy_input}" if galaxy_input.isdigit() else galaxy_input
        is_gal, gal_name, gal_id = check_galaxy_mention(galaxy_check_input, logger)
        logger.debug(f"AddModal: check_galaxy_mention({galaxy_check_input}) returned is_gal={is_gal}, gal_name={gal_name}, gal_id={gal_id}")
        if not is_gal or not (1 <= int(gal_id) <= 256):
            logger.warning(f"Invalid galaxy input: {galaxy_input}")
            await interaction.response.send_message("Galaxy must be 1-256 or a valid name.", ephemeral=USE_EPHEMERAL)
            return
        galaxy = str(gal_id)

        if not validate_address(address):
            logger.warning(f"Invalid address: {address}")
            await interaction.response.send_message("Address must be a 12-digit hex number starting with 1-6.", ephemeral=USE_EPHEMERAL)
            return

        locations = load_locations(filename, logger)
        if find_location_by_galaxy_address(galaxy, address, filename):
            logger.warning(f"Duplicate galaxy+address combination: galaxy={galaxy}, address={address}")
            await interaction.response.send_message("This galaxy+address combination already exists.", ephemeral=USE_EPHEMERAL)
            return

        if name.lower() in [n.lower() for n in locations.keys()]:
            logger.warning(f"Duplicate name (case-insensitive): {name}")
            await interaction.response.send_message(f"Name '{name}' already exists (case-insensitive). Please choose a unique name.", ephemeral=USE_EPHEMERAL)
            return

        logger.debug(f"AddModal: Attempting to register {name}")
        if register_location(name, galaxy, address, description, filename=filename, logger=logger):
            logger.info(f"AddModal: Successfully registered {name}")
            response = (
                f"Location added successfully:\n"
                f"- Name: {name}\n"
                f"- Galaxy: {galaxy} ({gal_name})\n"
                f"- Address: {address}\n"
                f"- Description: {description}\n"
                f"- URL: https://glyphs.had.sh/{galaxy}-{address}"
            )
            await interaction.response.send_message(response, ephemeral=USE_EPHEMERAL)
        else:
            logger.error(f"AddModal: Failed to register {name}")
            await interaction.response.send_message("Failed to add location.", ephemeral=USE_EPHEMERAL)

class RemoveModal(ui.Modal, title="Remove Location"):
    galaxy = ui.TextInput(label="Galaxy (1-256 or name)", placeholder="e.g., 3 or Eissentam", required=True)
    address = ui.TextInput(label="Address (12-digit hex)", placeholder="e.g., 6C8B7A654321", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        filename = get_channel_filename(interaction.channel_id)
        galaxy_input = self.galaxy.value
        address = self.address.value.upper()

        logger.info(f"RemoveModal: Processing galaxy={galaxy_input}, address={address}, file={filename}")
        galaxy_check_input = f"galaxy {galaxy_input}" if galaxy_input.isdigit() else galaxy_input
        is_gal, _, gal_id = check_galaxy_mention(galaxy_check_input, logger)
        logger.debug(f"RemoveModal: check_galaxy_mention({galaxy_check_input}) returned is_gal={is_gal}, gal_id={gal_id}")
        if not is_gal or not (1 <= int(gal_id) <= 256):
            logger.warning(f"Invalid galaxy input: {galaxy_input}")
            await interaction.response.send_message("Galaxy must be 1-256 or a valid name.", ephemeral=USE_EPHEMERAL)
            return
        galaxy = str(gal_id)

        if not validate_address(address):
            logger.warning(f"Invalid address: {address}")
            await interaction.response.send_message("Address must be a 12-digit hex number starting with 1-6.", ephemeral=USE_EPHEMERAL)
            return

        locations = load_locations(filename, logger)
        matched_name = None
        for name, data in locations.items():
            if data["galaxy"] == galaxy and data["address"] == address:
                matched_name = name
                break

        if matched_name:
            logger.info(f"RemoveModal: Found {matched_name} to remove")
            del locations[matched_name]
            save_locations(locations, filename, logger)
            logger.info(f"RemoveModal: Removed {matched_name} and saved locations")
            await interaction.response.send_message(f"Location '{matched_name}' removed successfully.", ephemeral=USE_EPHEMERAL)
        else:
            logger.warning(f"RemoveModal: No location found for galaxy={galaxy}, address={address}")
            await interaction.response.send_message("Location not found.", ephemeral=USE_EPHEMERAL)

class ModifyModal(ui.Modal, title="Modify Location"):
    identifier = ui.TextInput(label="Name or Address", placeholder="e.g., Eden Prime or 48D23456E9AF", required=True)
    new_galaxy = ui.TextInput(label="New Galaxy (1-256 or name, optional)", placeholder="e.g., 5", required=False)
    new_description = ui.TextInput(label="New Description (optional)", placeholder="e.g., Modified world", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        filename = get_channel_filename(interaction.channel_id)
        identifier = self.identifier.value
        new_galaxy_input = self.new_galaxy.value
        new_desc = self.new_description.value

        logger.info(f"ModifyModal: Processing identifier={identifier}, new_galaxy={new_galaxy_input}, new_desc={new_desc}, file={filename}")
        locations = load_locations(filename, logger)
        
        # Identify the location by name (partial match) or address
        name = None
        if validate_address(identifier.upper()):
            address = identifier.upper()
            for n, data in locations.items():
                if data["address"] == address:
                    name = n
                    break
        else:
            matches = [(n, fuzz.partial_ratio(identifier.lower(), n.lower())) for n in locations.keys()]
            matches = [m for m in matches if m[1] >= 80]
            matches.sort(key=lambda x: x[1], reverse=True)
            
            if len(matches) == 1:
                name = matches[0][0]
            elif 1 < len(matches) <= 5:
                response = "Multiple locations match your input. Please use a more unique name or the address:\n"
                response += "\n".join(f"- {m[0]}" for m in matches)
                logger.warning(f"ModifyModal: {len(matches)} partial matches found: {', '.join(m[0] for m in matches)}")
                await interaction.response.send_message(response, ephemeral=USE_EPHEMERAL)
                return
            elif len(matches) > 5:
                response = f"Multiple locations match your input (5 out of {len(matches)} shown). Please use a more unique name or the address:\n"
                response += "\n".join(f"- {m[0]}" for m in matches[:5])
                logger.warning(f"ModifyModal: {len(matches)} partial matches found, showing 5: {', '.join(m[0] for m in matches[:5])}")
                await interaction.response.send_message(response, ephemeral=USE_EPHEMERAL)
                return
        
        if not name:
            logger.warning(f"ModifyModal: No location found for identifier={identifier}")
            await interaction.response.send_message("Location not found.", ephemeral=USE_EPHEMERAL)
            return

        current_galaxy = locations[name]["galaxy"]
        current_address = locations[name]["address"]
        current_desc = locations[name]["description"]

        new_galaxy = None
        if new_galaxy_input:
            new_gal_check_input = f"galaxy {new_galaxy_input}" if new_galaxy_input.isdigit() else new_galaxy_input
            is_new_gal, _, new_gal_id = check_galaxy_mention(new_gal_check_input, logger)
            logger.debug(f"ModifyModal: check_galaxy_mention({new_gal_check_input}) returned is_new_gal={is_new_gal}, new_gal_id={new_gal_id}")
            if not is_new_gal or not (1 <= int(new_gal_id) <= 256):
                logger.warning(f"Invalid new galaxy input: {new_galaxy_input}")
                await interaction.response.send_message("New galaxy must be 1-256 or a valid name.", ephemeral=USE_EPHEMERAL)
                return
            new_galaxy = str(new_gal_id)
        else:
            new_galaxy = current_galaxy

        new_address = current_address
        new_desc = new_desc if new_desc else current_desc

        logger.debug(f"ModifyModal: Attempting to modify {name} with galaxy={new_galaxy}, desc={new_desc}")
        if modify_location(name, current_galaxy, current_address, new_galaxy, new_address, new_desc, filename=filename, logger=logger):
            logger.info(f"ModifyModal: Successfully modified {name}")
            await interaction.response.send_message(f"Location '{name}' modified successfully.", ephemeral=USE_EPHEMERAL)
        else:
            logger.error(f"ModifyModal: Failed to modify {name}")
            await interaction.response.send_message("Failed to modify location. Check old values match.", ephemeral=USE_EPHEMERAL)

class PickResultModal(ui.Modal, title="Multiple Results Found"):
    def __init__(self, results, total_count):
        super().__init__()
        self.results = results[:10]
        self.total_count = total_count
        result_text = "\n".join(f"{i+1}. {r['name']} (Galaxy {r['galaxy']}, {r['address']})" for i, r in enumerate(self.results))
        if total_count > 10:
            result_text += f"\nShowing 10 out of {total_count} results."
        self.choice = ui.TextInput(label="Pick a number (1-10)", placeholder="e.g., 1", required=True)
        self.results_display = ui.TextInput(label="Results", default=result_text, style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        logger.info(f"PickResultModal: Processing choice input")
        try:
            choice = int(self.choice.value) - 1
            if 0 <= choice < len(self.results):
                result = self.results[choice]
                response = f"Selected: {result['name']} (Galaxy {result['galaxy']}, {result['address']})\n{result['description']}"
                logger.info(f"PickResultModal: Selected result: {result['name']}")
                await interaction.response.send_message(response, ephemeral=USE_EPHEMERAL)
            else:
                logger.warning(f"PickResultModal: Invalid choice: {self.choice.value}")
                await interaction.response.send_message("Invalid choice. Please pick a number within the range.", ephemeral=USE_EPHEMERAL)
        except ValueError:
            logger.warning(f"PickResultModal: Non-numeric choice entered: {self.choice.value}")
            await interaction.response.send_message("Please enter a valid number.", ephemeral=USE_EPHEMERAL)

@tree.command(name="glyphs", description="Manage and search locations")
@app_commands.describe(action="Action or search string (e.g., find, top, or 'crystal falls')")
async def glyphs(interaction: discord.Interaction, action: str):
    filename = get_channel_filename(interaction.channel_id)
    logger.info(f"Command received: /glyphs {action} in channel {interaction.channel.name}, using file {filename}, issued by {interaction.user.display_name} ({interaction.user.id})")
    parts = action.strip().split(maxsplit=1)
    first_word = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    commands = ["find", "top", "remove", "modify", "add", "help"]
    best_match = max(commands, key=lambda cmd: fuzz.ratio(first_word, cmd), default=None)
    threshold = 80
    matched_command = best_match if fuzz.ratio(first_word, best_match) >= threshold else None

    if matched_command in ["remove", "modify", "add"]:
        if not any(role.id == PRIVILEGED_ROLE_ID for role in interaction.user.roles):
            logger.warning(f"Unauthorized attempt to execute {matched_command} by user {interaction.user.display_name} ({interaction.user.id})")
            await interaction.response.send_message("You are not authorized to perform this action.", ephemeral=USE_EPHEMERAL)
            return

    if len(parts) == 1 and matched_command:
        if matched_command == "find":
            logger.warning("Find command used without search term")
            await interaction.response.send_message("Please use '/glyphs find <search term>' or '/glyphs <location>' for searching.", ephemeral=USE_EPHEMERAL)
        elif matched_command == "top":
            logger.info("Processing /glyphs top")
            top_locs = list_top_locations(10, filename=filename, logger=logger)
            response = f"```\n{format_locations_list(top_locs)}\n```"
            logger.debug(f"Top 10 locations retrieved: {len(top_locs)} entries")
            await interaction.response.send_message(response, ephemeral=USE_EPHEMERAL)
        elif matched_command == "remove":
            logger.debug("Opening RemoveModal")
            await interaction.response.send_modal(RemoveModal())
        elif matched_command == "modify":
            logger.debug("Opening ModifyModal")
            await interaction.response.send_modal(ModifyModal())
        elif matched_command == "add":
            logger.debug("Opening AddModal")
            await interaction.response.send_modal(AddModal())
        elif matched_command == "help":
            logger.info("Processing /glyphs help")
            help_text = (
                "Commands:\n"
                "- `/glyphs find <term>`: Search locations by name or description.\n"
                "- `/glyphs top`: List top 10 most returned locations.\n"
                "- `/glyphs add`: Add a location (restricted to privileged users).\n"
                "- `/glyphs remove`: Remove a location (restricted to privileged users).\n"
                "- `/glyphs modify`: Modify a location's galaxy or description (restricted to privileged users).\n"
                "- `/glyphs <location>`: Direct search for a location."
            )
            await interaction.response.send_message(help_text, ephemeral=USE_EPHEMERAL)
    else:
        await interaction.response.defer(ephemeral=USE_EPHEMERAL)
        search_term = rest if matched_command == "find" else action
        logger.info(f"Searching for: {search_term}")
        name_result = find_location_in_string(search_term, filename=filename, logger=logger)
        locations = load_locations(filename, logger)
        desc_results = []
        for name, data in locations.items():
            if fuzz.partial_ratio(search_term.lower(), data["description"].lower()) >= 80:
                if not name_result or (name_result["galaxy"] != data["galaxy"] or name_result["address"] != data["address"]):
                    desc_results.append((name, data))

        results = []
        if name_result:
            matched_name = None
            for name, data in locations.items():
                if (data["galaxy"] == name_result["galaxy"] and 
                    data["address"] == name_result["address"]):
                    matched_name = name
                    break
            if matched_name:
                results.append({"name": matched_name, **name_result})
            else:
                results.append({"name": f"matched_location_{search_term}", **name_result})
        results.extend({"name": name, **data} for name, data in desc_results if name not in [r["name"] for r in results])

        logger.debug(f"Search returned {len(results)} results")
        if not results:
            logger.info(f"No results found for {search_term}")
            await interaction.followup.send("No matching locations found.", ephemeral=USE_EPHEMERAL)
        elif len(results) == 1:
            result = results[0]
            response = (
                f"Found: {result['name']} (Galaxy {result['galaxy']}, {result['address']})\n"
                f"{result['description']}\n"
                f"URL: https://glyphs.had.sh/{result['galaxy']}-{result['address']}"
            )
            logger.info(f"Single result found: {result['name']}")
            await interaction.followup.send(response, ephemeral=USE_EPHEMERAL)
        else:
            logger.info(f"Multiple results found: {len(results)}")
            await interaction.followup.send_modal(PickResultModal(results, len(results)))

@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user}")
    await tree.sync()
    logger.info("Commands synced with Discord")

import os

client.run(os.getenv('DISCORD_TOKEN'))
