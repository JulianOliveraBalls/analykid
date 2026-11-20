"""Fábrica de modelos.

El agente (agente.py) solo llama a get_model(); no sabe qué proveedor hay
detrás. Para cambiar de modelo se editan las variables del .env.
"""
import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

load_dotenv()

# Reintentos ante 429 y errores transitorios: los resuelve el cliente de cada
# proveedor, con espera exponencial (por eso no hay middleware de reintentos).
REINTENTOS = 6
TIMEOUT_S = 120


def _exigir(variable: str) -> None:
    if not os.getenv(variable):
        raise RuntimeError(f"Falta {variable}. Copiá .env.example a .env y completalo.")


def get_embeddings():
    """Modelo de embeddings para el RAG: Google, vía API (capa gratuita)."""
    _exigir("GOOGLE_API_KEY")
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")


def get_model() -> BaseChatModel:
    """Gemini (principal) u OpenRouter (respaldo), según MODEL_PROVIDER."""
    provider = os.getenv("MODEL_PROVIDER", "google_genai")
    name = os.getenv("MODEL_NAME", "gemini-3.5-flash-lite")

    if provider == "google_genai":
        _exigir("GOOGLE_API_KEY")
        # include_thoughts=True: Gemini devuelve resúmenes de su razonamiento.
        # Los Gemini 3+ (los Flash Lite sobre todo) solo los devuelven si además
        # se fija THINKING_LEVEL (low | medium | high); Gemini 2.5 no lo usa.
        nivel = os.getenv("THINKING_LEVEL")
        return init_chat_model(
            name, model_provider=provider, temperature=0, include_thoughts=True,
            max_retries=REINTENTOS, timeout=TIMEOUT_S,
            **({"thinking_level": nivel} if nivel else {}),
        )

    if provider == "openrouter":
        _exigir("OPENROUTER_API_KEY")
        from langchain_openrouter import ChatOpenRouter

        # ChatOpenRouter lee OPENROUTER_API_KEY del entorno.
        return ChatOpenRouter(
            model=name, temperature=0, reasoning={"effort": "high", "summary": "auto"},
            max_retries=REINTENTOS, request_timeout=TIMEOUT_S,
        )

    raise RuntimeError(
        f"MODEL_PROVIDER «{provider}» no soportado. Opciones: google_genai, openrouter."
    )
