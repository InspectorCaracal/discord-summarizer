from dataclasses import dataclass
from typing import Optional
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from discord.ext import tasks, commands
import logging

import yaml

logger = logging.getLogger("discord")


START_DIFF = timedelta(minutes=15)
END_DIFF = timedelta(hours=1)


@dataclass(order=True)
class MessageData:
    """Data class to represent a collected message."""

    timestamp: datetime  # defined first for sorting purposes
    id: int
    author: int
    content: str
    attachments: list[str]


@dataclass
class ChannelStatus:
    """Data class to hold channel status information."""

    checked_at: datetime
    active: bool


@dataclass
class BotData:
    """Data class to hold bot state and configuration."""

    last_validated: dict[str, ChannelStatus]
    tracked_channels: Optional[set[str]] = None  # Set of channel IDs being tracked


class SummarizerCog(commands.Cog):
    """Cog that handles yaml data, summarizer, commands, and helper methods."""

    def __init__(
        self,
        bot,
        summarizer,
        yaml_file="discord_summarizer.yaml",
        whitelist_mode: bool = True,
    ):
        self.bot = bot
        self.summarizer = summarizer
        self.yaml_file = yaml_file
        self.yaml_data = BotData(last_validated={})
        self.whitelist_mode = whitelist_mode
        self.message_collection = defaultdict(lambda: defaultdict(list))

        try:
            yaml_data = self.load_yaml()
            self.yaml_data = yaml_data
        except Exception as e:
            logger.error(f"Error loading YAML data: {e}")

        if not whitelist_mode:
            logger.debug(
                "Overriding YAML data to disable whitelist mode and track all channels."
            )
            self.yaml_data.tracked_channels = None

    def load_yaml(self):
        yaml_data = BotData(last_validated={})
        logger.debug(f"Reading persistent data from {self.yaml_file} ...")
        try:
            with open(self.yaml_file, "r") as f:
                if data := yaml.safe_load(f):
                    yaml_data = BotData(**data)
                    logger.debug(f"Loaded YAML data: {yaml_data}")
        except FileNotFoundError:
            logger.warning(f"{self.yaml_file} not found. Starting with empty data.")
        return yaml_data

    def save_yaml(self):
        """Writes the current self.yaml_data dictionary to the YAML_FILE."""
        try:
            with open(self.yaml_file, "w") as f:
                yaml.dump(self.yaml_data, f)
            logger.info(f"YAML file {self.yaml_file} updated successfully.")
        except Exception as e:
            logger.error(f"Error writing to YAML file {self.yaml_file}: {e}")

    async def _fetch_message_history(self, guild, channel):
        """Helper method to fetch message history for a channel after a certain timestamp."""
        default_timestamp = datetime.now(tz=timezone.utc) - timedelta(hours=3)
        time_data = self.yaml_data.last_validated.get(str(channel.id))
        if time_data is None:
            time_data = ChannelStatus(checked_at=default_timestamp, active=False)
        messages = []
        try:
            async for message in channel.history(
                limit=None, after=time_data.checked_at
            ):
                message_data = MessageData(
                    id=message.id,
                    author=message.author.id,
                    content=message.content,
                    timestamp=message.created_at,
                    attachments=[att.url for att in message.attachments],
                )
                messages.append(message_data)
            logger.info(
                f"Fetched {len(messages)} messages from guild ID {guild.id}, channel ID {channel.id} since {time_data.checked_at}."
            )
        except Exception as e:
            logger.error(
                f"Error fetching history for guild ID {guild.id}, channel ID {channel.id}: {e}"
            )
        self.message_collection[guild.id][channel.id].extend(messages)

        # Apply conversation-chunking strategy over the entire block of messages
        if len(messages) >= 5:
            messages.sort()
            conversation_chunks = []
            current_chunk = []
            in_conversation = False
            validate_stamp = None

            for msg in messages:
                current_chunk.append(msg)
                if len(current_chunk) < 5:
                    continue
                if not in_conversation:
                    if current_chunk[-5].timestamp < msg.timestamp - START_DIFF:
                        # we are in a conversation now!
                        in_conversation = True
                        current_chunk = current_chunk[-5:]
                        validate_stamp = current_chunk[0].timestamp
                        continue
                else:
                    if current_chunk[-5].timestamp > msg.timestamp - END_DIFF:
                        # conversation has gone idle, finalize this chunk
                        conversation_chunks.append(current_chunk)
                        current_chunk = []  # Start fresh
                        in_conversation = False
                        validate_stamp = msg.timestamp
                        continue

            # slap the conversation/timestamp status onto the channel statuses
            if validate_stamp:
                self.yaml_data.last_validated[str(channel.id)] = ChannelStatus(
                    checked_at=validate_stamp, active=in_conversation
                )
                self.save_yaml()
            # and replace the remembered messages with only the unhandled tail
            self.message_collection[guild.id][channel.id] = current_chunk

            # summarize completed chunks
            for chunk in conversation_chunks:
                logger.debug(
                    f"Summarizing historical conversation chunk with {len(chunk)} messages from channel ID {channel.id}"
                )
                await self.summarizer.summarize_messages(  # type: ignore
                    channel_name=channel.name, server_name=guild.name, messages=chunk
                )

    async def track_channel(self, channel, track=True):
        """Add or remove a channel from the tracked channels set."""
        if self.yaml_data.tracked_channels is None:
            logger.debug(
                "Attempted to change tracking status for a channel while whitelist mode is disabled, for some reason."
            )
            return False  # No change needed since we're tracking everything anyway
        if track == (channel.id in self.yaml_data.tracked_channels):
            logger.debug(
                f"Track status '{track}' requested for channel ID '{channel.id}' but it's already {'tracked' if track else 'not tracked'}."
            )
            return False  # No change needed

        if track:
            channel_id_str = str(channel.id)
            self.yaml_data.tracked_channels.add(channel_id_str)
            fallback_time = datetime.now(tz=timezone.utc) - timedelta(hours=3)
            if str(channel.id) not in self.yaml_data.last_validated:
                self.yaml_data.last_validated[channel_id_str] = ChannelStatus(
                    checked_at=fallback_time, active=False
                )
                logger.debug(
                    f"Initialized last validated timestamp for channel ID {channel.id} to {self.yaml_data.last_validated[channel_id_str].checked_at}."
                )
            elif (
                self.yaml_data.last_validated[channel_id_str].checked_at < fallback_time
            ):
                self.yaml_data.last_validated[channel_id_str].checked_at = fallback_time
                self.yaml_data.last_validated[channel_id_str].active = False
                logger.debug(
                    f"Reset last validated timestamp for channel ID {channel.id} to {self.yaml_data.last_validated[channel_id_str].checked_at} due to being too old."
                )
            await self._fetch_message_history(channel.guild, channel)
            logger.info(f"Started tracking channel ID {channel.id}")
        else:
            self.yaml_data.tracked_channels.remove(channel.id)
            del self.message_collection[channel.guild.id][channel.id]
            logger.info(f"Stopped tracking channel ID {channel.id} and cleared history")

        self.save_yaml()
        return True

    @commands.command(name="track")
    @commands.has_permissions(administrator=True)
    async def track(self, ctx):
        """View or set tracking status for this channel (Admin only)."""
        # if not whitelisting, this is an effective no-op
        if self.yaml_data.tracked_channels is None:
            await ctx.send(
                "All channels are being tracked. Contact the bot owner to enable whitelist mode."
            )
            return
        args = ctx.message.content.split()
        msg = ""
        if len(args) == 1:
            # Show tracking status
            if ctx.channel.id in self.yaml_data.tracked_channels:
                msg = "✅ This channel is currently being tracked."
            else:
                msg = "❌ This channel is not being tracked."
        elif len(args) == 2:
            # Set tracking status
            action = args[1].lower()
            if action in ["on", "true", "1"]:
                try:
                    changed = await self.track_channel(ctx.channel, track=True)
                    msg = (
                        "✅ This channel is now being tracked."
                        if changed
                        else "This channel is already being tracked."
                    )
                except Exception as e:
                    logger.error(f"Error tracking channel ID {ctx.channel.id}: {e}")
                    msg = "⚠️ An error occurred while trying to track this channel."
            elif action in ["off", "false", "0"]:
                try:
                    changed = await self.track_channel(ctx.channel, track=False)
                    msg = (
                        "❌ This channel is no longer being tracked."
                        if changed
                        else "This channel is already not being tracked."
                    )
                except Exception as e:
                    logger.error(f"Error untracking channel ID {ctx.channel.id}: {e}")
                    msg = "⚠️ An error occurred while trying to untrack this channel."
        if not msg:
            logger.debug(f"Invalid track command arguments: {ctx.message.content}")
            msg = "⚠️ Invalid argument. Use `{pfx}track on` or `{pfx}track off`".format(
                pfx=self.bot.command_prefix
            )
        await ctx.send(msg)

    @tasks.loop(minutes=5)
    async def check_conversations(self):
        """Periodically check for active conversations."""
        # fetch current classification of idle vs active here to avoid state mutations
        active = []
        idle = []
        for channel_id, status in self.yaml_data.last_validated.items():
            if status.active:
                active.append(channel_id)
            else:
                idle.append(channel_id)
        time_to_active = datetime.now(tz=timezone.utc) - START_DIFF
        time_to_idle = datetime.now(tz=timezone.utc) - END_DIFF
        for gid in self.message_collection:
            for cid in self.message_collection[gid]:
                if str(cid) in idle:
                    # check if fifth-oldest message is within the last 15 minutes
                    messages = sorted(self.message_collection[gid][cid])
                    if len(messages) >= 5 and messages[-5].timestamp > time_to_active:
                        self.yaml_data.last_validated[str(cid)].active = True
                        logger.debug(f"Channel ID {cid} marked as active conversation.")
                elif str(cid) in active:
                    # check if fifth-oldest message is over an hour old
                    messages = sorted(self.message_collection[gid][cid])
                    if len(messages) >= 5 and messages[-5].timestamp < time_to_idle:
                        self.yaml_data.last_validated[str(cid)].active = False
                        logger.debug(
                            f"Channel ID {cid} marked as idle conversation. Triggering summary generation."
                        )
                        # don't await, we don't want to block the loop while waiting for the LLM response
                        self.summarizer.summarize_messages(  # type: ignore
                            channel_name=self.bot.get_channel(cid).name,
                            server_name=self.bot.get_channel(cid).guild.name,
                            messages=messages,
                        )
                        # clear the messages we just summarized
                        self.message_collection[gid][cid] = []
                self.yaml_data.last_validated[str(cid)].checked_at = (
                    time_to_active  # use backview window for better resume detection after downtime
                )
        # persist any state changes
        self.save_yaml()

    @check_conversations.before_loop
    async def before_check_conversations(self):
        logger.debug(
            "Waiting for bot to be ready before starting conversation checker..."
        )
        await self.bot.wait_until_ready()
        logger.debug("Bot is ready. Starting conversation checker task...")

    async def cog_load(self):
        """Called when the cog is loaded."""
        logger.debug("SummarizerCog loaded. Starting check_conversations task...")
        self.check_conversations.start()

    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the bot is ready - fetch history for tracked channels."""
        logger.info(f"Connected to {len(self.bot.guilds)} server(s)")
        guild_info = "\n".join(
            [f" - {guild.name} (ID: {guild.id})" for guild in self.bot.guilds]
        )
        logger.debug(guild_info)

        # rebuild in-memory message collection since last validated datetime for each trackable channel
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if (
                    self.yaml_data.tracked_channels is not None
                    and channel.id not in self.yaml_data.tracked_channels
                ):
                    logger.debug(
                        f"Skipping channel ID {channel.id} because it's not being tracked."
                    )
                    continue
                await self._fetch_message_history(guild, channel)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Called when a message is received - collect if tracked."""
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return

        # check if channel is being tracked
        if (
            self.yaml_data.tracked_channels is not None
            and message.channel.id not in self.yaml_data.tracked_channels
        ):
            logger.debug(
                f"Skipping message from channel ID {message.channel.id} because it's not being tracked."
            )
            return

        # Collect the message
        guild_id = message.guild.id if message.guild else "DM"
        channel_id = message.channel.id
        logger.debug(
            f"Collecting message from guild ID {guild_id}, channel ID {channel_id}"
        )

        message_data = MessageData(
            id=message.id,
            author=message.author.id,
            content=message.content,
            timestamp=message.created_at,
            attachments=[att.url for att in message.attachments],
        )

        self.message_collection[guild_id][channel_id].append(message_data)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Called when the bot joins a new server."""
        logger.info(f"Joined new server: {guild.name} (ID: {guild.id})")

        # fetch message history for all channels in this guild that are being tracked
        for channel in guild.text_channels:
            if (
                self.yaml_data.tracked_channels is not None
                and channel.id not in self.yaml_data.tracked_channels
            ):
                logger.debug(
                    f"Skipping channel ID {channel.id} because it's not being tracked."
                )
                continue
            await self._fetch_message_history(guild, channel)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """Called when the bot is removed from a server."""
        logger.info(f"Removed from server: {guild.name} (ID: {guild.id})")

        # Clean up message collection for this guild
        if guild.id in self.message_collection:
            if self.yaml_data.tracked_channels is not None:
                for channel_id in self.message_collection[guild.id]:
                    self.yaml_data.tracked_channels.remove(str(channel_id))
                # save yaml data
                self.save_yaml()
                logger.debug(f"Removed channels from tracking for guild ID {guild.id}.")
            del self.message_collection[guild.id]
            logger.debug(f"Cleared message history for guild ID {guild.id}.")
