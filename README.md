# RAG Project — fase 1: chatbot

Single-turn chatbot met Streamlit en een OpenAI-compatible endpoint. Standaard staat de client op de gratis Gemini Flash-tier; later wisselen naar `gpt-4.1-mini` is alleen een kwestie van `LLM_BASE_URL`, `LLM_API_KEY` en `LLM_MODEL` aanpassen.

De RAG-pipeline volgt in fase 2. Zie `AGENTS.md` voor de volledige afspraken.

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
# vul LLM_API_KEY in .env in (key via Google AI Studio)
python -m streamlit run src/rag_app/app.py
```

Zonder activeren:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m streamlit run src/rag_app/app.py
```

## Checks

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest
```

De tests hebben geen API-key of netwerk nodig; de LLM-client is gemockt.

## Gedrag

- De UI toont de gespreksgeschiedenis, maar per vraag gaan alleen de systeemprompt en de huidige vraag naar het model.
- Antwoorden streamen; bij 429, 401, timeouts en 5xx verschijnt een Nederlandse foutmelding.
- Geen persistentie: het gesprek verdwijnt bij een herstart.
