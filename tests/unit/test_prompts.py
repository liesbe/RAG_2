"""Tests for single-turn prompt construction."""

from rag_app.llm.prompts import SYSTEM_PROMPT, build_messages


def test_build_messages_contains_only_system_and_current_question() -> None:
    messages = build_messages("Wat is RAG?")

    assert len(messages) == 2
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1] == {"role": "user", "content": "Wat is RAG?"}


def test_build_messages_does_not_reuse_previous_messages() -> None:
    first = build_messages("Eerste vraag")
    second = build_messages("Tweede vraag")

    assert len(second) == 2
    assert "Eerste vraag" not in str(second)
    assert first != second
