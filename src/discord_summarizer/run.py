"""
Discord Bot - Message Collector
Reads messages and collects them into lists sorted by server and channel.
"""

import asyncio
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from .bot import SummarizerCog
from .llm import Summarizer

import logging

logger = logging.getLogger("discord-summarizer")


def main():
    """Main entry point for the bot."""
    # Load environment variables from .env file
    load_dotenv()

    token = os.getenv("DISCORD_BOT_TOKEN")

    if not token or token == "CHANGE_ME":
        print("Error: DISCORD_BOT_TOKEN environment variable not set!")
        print("Please set your Discord bot token:")
        print("  export DISCORD_BOT_TOKEN='your_token_here'")
        print("Or create a .env file with DISCORD_BOT_TOKEN=your_token_here")
        return

    llm_api_key = os.getenv("LLM_API_KEY")
    if not llm_api_key:
        print(
            "Warning: LLM_API_KEY environment variable not set. If you are NOT running local inference, this will probably be a problem!"
        )

    # ensure summary output directory exists
    if not os.path.exists("summaries"):
        os.makedirs("summaries")

    llm_base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    llm_model = os.getenv("LLM_MODEL", "gpt-5-mini")

    # set logging level
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=log_level)
    print(f"Logging level set to {log_level}")

    summarizer = Summarizer(api_key=llm_api_key, base_url=llm_base_url, model=llm_model)

    whitelist_mode = os.getenv("WHITELIST_MODE", "true").lower()
    if whitelist_mode in ["true", "1", "on"]:
        logger.info(
            f"Whitelist mode enabled. Collecting tracked channels from YAML data."
        )
        whitelist_mode = True
    else:
        logger.info("Whitelist mode disabled. Tracking all channels.")
        whitelist_mode = False

    # get prefix from environment variable if set
    if prefix := os.getenv("COMMAND_PREFIX", None):
        logger.info(f"Using command prefix: {prefix}")

    intents = discord.Intents.default()
    intents.message_content = True  # Required to read message content
    intents.messages = True
    intents.guilds = True
    discord_bot = commands.Bot(command_prefix=prefix or "!", intents=intents)
    cog = SummarizerCog(discord_bot, summarizer, whitelist_mode=whitelist_mode)
    asyncio.create_task(discord_bot.add_cog(cog))

    # start bot!
    print("Starting Discord Summarizer bot...")
    discord_bot.run(token)


if __name__ == "__main__":
    main()
