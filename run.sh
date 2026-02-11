#!/bin/bash

# Quick start script for Discord Message Collector Bot

echo "Discord Summarizer - Checking setup requirements..."
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CLEAR='\033[0m'

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}No .env file found!${CLEAR}"
    cp .env.example .env
    echo -e "${YELLOW}The example .env.example file has been copied to .env but needs to be configured.${CLEAR}"
    echo "Exiting."
    exit 1
fi

# Check if token is set
source .env
if [ -z "$DISCORD_BOT_TOKEN" ] || [ "$DISCORD_BOT_TOKEN" = "CHANGE_ME" ]; then
    echo -e "${RED}DISCORD_BOT_TOKEN not properly set in .env file!${CLEAR}"
    echo "Come on, you got this. Exiting again."
    exit 1
fi

if [ ! -f .venv ]; then
    echo -e "${YELLOW}No virtual environment found! Making one and installing...${CLEAR}"
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .
else
    echo -e "${GREEN}Activating virtual environment...${CLEAR}"
    source .venv/bin/activate
fi

echo -e "Lauching bot script..."
# Run the bot
discord_summarizer
