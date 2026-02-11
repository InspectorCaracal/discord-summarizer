import json
import openai
import logging
from typing import TYPE_CHECKING

logger = logging.getLogger("summarizer")

if TYPE_CHECKING:
    from .bot import MessageData


class Summarizer:
    def __init__(self, api_key: str | None, base_url: str, model: str):
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def summarize_messages(
        self, channel_name: str, server_name: str, messages: list[MessageData]
    ):
        if not messages:
            logger.warning(f"Summarize somehow called with empty message list??")
            return

        messages = sorted(messages)
        message_text = "\n".join(
            "[{timestamp}] {author}: {content}".format(
                timestamp=msg.timestamp.isoformat(),
                author=msg.author,
                content=msg.content,
            )
            for msg in messages
        )

        # build the request
        request_data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a summarization agent responsible for effectively summarizing Discord conversations. Each summary must begin with a short, one-sentence description of the primary topic, followed by a concise paragraph covering only the most significant points. Avoid mentioning specific user names unless their identity is integral to the topic. Focus on the content of the discussion.",
                },
                {
                    "role": "user",
                    "content": f"Summarize the following conversation from the channel {channel_name} on the {server_name} server:\n\n{message_text}",
                },
            ],
            "temperature": 0.5,
            "max_tokens": 500,
            "stream": False,
        }

        logger.debug("Sending summarization request to LLM...")

        try:
            result = self.client.chat.completions.create(**request_data)
        except Exception as e:
            logger.error(f"Error during summarization: {e}")
            return

        logger.debug(f"LLM response: {result}")
        summary = result.choices[0].message.content.strip()
        logger.info(f"Summary generated for {server_name}#{channel_name}")

        # get last message timestamp from the chunk being summarized
        last_timestamp = messages[-1].timestamp.isoformat()

        obj = {"summary": summary, "timestamp": last_timestamp}
        with open(f"summaries/{server_name}_{channel_name}.jsonl", "a") as f:
            f.write(json.dumps(obj) + "\n")
