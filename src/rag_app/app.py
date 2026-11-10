"""Streamlit entrypoint for the phase 1 single-turn chatbot."""

from __future__ import annotations

import streamlit as st
from pydantic import ValidationError

from rag_app.config import get_settings
from rag_app.llm.client import LLMClient, LLMError

st.set_page_config(page_title="RAG Project - Chatbot", page_icon="💬", layout="centered")


@st.cache_resource
def _get_client() -> LLMClient:
    """Create one client for the lifetime of the Streamlit process."""
    return LLMClient(get_settings())


def _render_history() -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def main() -> None:
    try:
        settings = get_settings()
    except ValidationError:
        st.error(
            "Configuratie ontbreekt of is ongeldig. "
            "Kopieer `.env.example` naar `.env` en vul `LLM_API_KEY` in."
        )
        st.stop()

    st.title("Chatbot")
    st.caption(f"Model: `{settings.llm_model}` · single-turn")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    with st.sidebar:
        st.header("Instellingen")
        st.caption(f"Model: `{settings.llm_model}`")
        if st.button("Gesprek wissen"):
            st.session_state.messages = []
            st.rerun()
        st.caption("Alleen je huidige vraag wordt naar het model gestuurd.")

    _render_history()

    prompt = st.chat_input("Stel je vraag...")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    client = _get_client()
    with st.chat_message("assistant"):
        try:
            with st.spinner("Antwoord wordt gegenereerd..."):
                reply = st.write_stream(client.stream_reply(prompt))
        except LLMError as exc:
            st.error(str(exc))
            return

    if isinstance(reply, str) and reply:
        st.session_state.messages.append({"role": "assistant", "content": reply})


main()
