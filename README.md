# RAG Project — fase 1: chatbot

Single-turn chatbot met Streamlit en een OpenAI-compatible endpoint. Standaard staat de client op de gratis Gemini Flash-tier; later wisselen naar `gpt-4.1-mini` is alleen een kwestie van `LLM_BASE_URL`, `LLM_API_KEY` en `LLM_MODEL` aanpassen.

De RAG-pipeline volgt in fase 2. Zie `AGENTS.md` voor de volledige afspraken.

## Setup

### GitHub Codespaces

De devcontainer gebruikt Python 3.12, maakt `.venv` aan en installeert het project met de
ontwikkelafhankelijkheden wanneer de container wordt aangemaakt of opnieuw gebouwd. VS Code en de
automatisch gestarte app gebruiken die omgeving. Voer na wijzigingen aan
`.devcontainer/devcontainer.json` **Codespaces: Rebuild Container** uit om de configuratie toe te
passen.

### Lokale setup (Windows)

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

## Tijdelijk testen op Streamlit Community Cloud

De app kan tijdelijk publiek worden gedeeld via [Streamlit Community Cloud](https://share.streamlit.io).
Iedereen met de URL kan dan vragen stellen met jouw Gemini API-key; houd rekening met je quota en
verwijder de app zodra je klaar bent. Inactiviteit maakt de app alleen slapend, niet privé.

1. Push de repository naar GitHub. `requirements.txt` installeert het project en de dependencies uit
   `pyproject.toml`.
2. Meld je aan op Streamlit Community Cloud en kies **Create app**.
3. Selecteer repository en branch, en gebruik als entrypoint
   `src/rag_app/app.py`. Kies bij **Advanced settings** Python 3.12.
4. Voeg bij **Secrets** alleen je eigen API-key toe:

   ```toml
   LLM_API_KEY = "jouw-eigen-key"
   ```

   Plak de key uitsluitend in Cloud Secrets, niet in GitHub of in dit bestand. Streamlit maakt na
   deployment een `https://…streamlit.app`-URL die je kunt delen.
5. Klaar met testen? Open je app in de Streamlit Cloud-workspace, kies het menu **⋮** en vervolgens
   **Delete**. Bevestig het verwijderen; daarmee stopt de publieke URL. Je kunt later opnieuw
   deployen. Alleen de key uit Secrets verwijderen stopt de toegang tot de LLM, maar maakt de app
   zelf niet privé.
