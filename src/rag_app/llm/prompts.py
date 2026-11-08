"""Prompt construction for the phase 1 single-turn chatbot."""

from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

SYSTEM_PROMPT = (
    "Je bent een behulpzame, beknopte assistent. "
    "Antwoord in de taal van de gebruiker; is die onduidelijk, antwoord dan in het Nederlands. "
    "Verzin geen feiten: als je iets niet weet, zeg dat expliciet."
)


def build_messages(user_message: str) -> list[ChatCompletionMessageParam]:
    """Build a single-turn message list: system prompt plus the current question.

    Earlier conversation is deliberately not included; the UI only shows history.
    """
    system: ChatCompletionSystemMessageParam = {
        "role": "system",
        "content": SYSTEM_PROMPT,
    }
    user: ChatCompletionUserMessageParam = {
        "role": "user",
        "content": user_message,
    }
    return [system, user]
