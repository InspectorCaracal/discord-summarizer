# Discord Summarizer

A Discord bot for automatically tracking conversational activity and recording LLM-generated summaries.

**IMPORTANT NOTE** - I have not actually tried using this yet. I made it because someone else wanted it and I don't have perms on any servers active enough to use it.

## Features

- Works with any OpenAI-compatible API - including local.
- Uses simple .env file configuration (or regular env variables if you're feeling fancy)
- Configuration file can toggle between whitelisted channels and summarizing everything.
- Persists state in a simple YAML file.
- Does NOT store ANY messages to disk! Messages are kept in-memory only and cleared after being summarized.

## Setup

### Requirements

- A Discord bot token
- An LLM API key (optional if running local)
- A reasonable level of self-sufficiency

### Installation

If you're on Linux, I made a nice little script in `run.sh` that will do everything for you that you're welcome to use or ignore. Otherwise, standard procedures for your favorite python setup apply.

### Configuration

Copy the `.env.example` file to `.env` and change it to suit your needs. At the very least, **you definitely need `DISCORD_BOT_TOKEN`**. Most likely, you'll want to change the API and API keys too.

`.env.example` also has some explanatory comments of what each one does.

## Running the Bot

See above about `run.sh` or you can do `python src/main.py` by hand.

For it to actually *do* anything, of course, you'll need to invite the bot to whatever servers you want it on. I'll leave that in your capable hands.

## Notes

The summaries are dumped into appropriately named `.jsonl` files in a `summaries/` directory, in, you guessed it, JSONL format. Not the most human-readable option, but convenient for parsing by whatever else you want to use the summaries.

## Contributing

Let's be honest, nobody is going to contribute to this. But hey. If you find a bug and want to PR a fix, go for it, that would be great.