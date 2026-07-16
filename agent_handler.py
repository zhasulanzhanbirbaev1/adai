import os
import logging
from anthropic import Anthropic

from database import (
    get_agent, get_or_create_conversation,
    get_conversation_messages, save_agent_message,
)

logger = logging.getLogger(__name__)
_client = None


def _get_client():
    global _client
    if _client is None:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in .env")
        _client = Anthropic(api_key=key)
    return _client


def chat(agent_id: int, session_id: str, user_message: str) -> str:
    agent = get_agent(agent_id)
    if not agent:
        return "Агент не найден или отключён."

    conv_id = get_or_create_conversation(agent_id, session_id)

    history = get_conversation_messages(conv_id, limit=19)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_message})
    save_agent_message(conv_id, "user", user_message)

    try:
        client = _get_client()
        response = client.messages.create(
            model=agent["model"] or "claude-sonnet-4-6",
            max_tokens=1024,
            system=agent["system_prompt"],
            messages=messages,
        )
        reply = response.content[0].text
    except RuntimeError as e:
        logger.error("Anthropic client error: %s", e)
        reply = "Сервис временно недоступен. Попробуйте позже."
    except Exception as e:
        logger.error("Anthropic API error: %s", e)
        reply = "Произошла ошибка. Попробуйте ещё раз."

    save_agent_message(conv_id, "assistant", reply)
    return reply
