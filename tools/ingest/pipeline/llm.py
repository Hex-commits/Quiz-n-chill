"""The locally hosted model, as a LangChain chat model.

Ollama's `/api/chat` accepts a JSON Schema in its `format` field and constrains
decoding to match it (Ollama >= 0.5). That is the local equivalent of a hosted
API's structured outputs, and it is what makes a 9B model usable here at all --
without it, a small model returns prose around its JSON, or trailing commas, or
a plausible-looking object with the wrong keys.

`structured()` below is how that field gets set. The schema must be a **dict**:
hand `with_structured_output` a Pydantic class instead and LangChain calls
`model_json_schema()` on it, which omits every defaulted field from `required`
-- and a 9B model duly returns `subject_slug: ""`, `title: ""` and calls it
done. `generate.question_schema()` exists for exactly that reason.

Constrained decoding guarantees the *shape*, never the *content*: the model can
still return a pairing that is simply wrong, or the same answer twice under
different labels. That is what the `check` and `review` steps are for, and why
`graph.py` loops.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from langchain_core.runnables import Runnable
from langchain_ollama import ChatOllama

DEFAULT_BASE_URL = "http://localhost:11435"
DEFAULT_MODEL = "glm4:9b"

DEFAULT_TIMEOUT = 600.0

DEFAULT_TEMPERATURE = 0.3
DEFAULT_NUM_CTX = 8192


class LLMError(RuntimeError):
    pass


def chat_model(
    *,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    num_ctx: int = DEFAULT_NUM_CTX,
    timeout: float = DEFAULT_TIMEOUT,
) -> ChatOllama:
    """One chat model, shared by every node in the graph."""
    return ChatOllama(
        base_url=base_url,
        model=model,
        temperature=temperature,
        num_ctx=num_ctx,
        client_kwargs={"timeout": timeout},
    )


def structured(model: ChatOllama, schema: dict) -> Runnable:
    """Bind `schema` to Ollama's `format` field and parse the reply as JSON.

    A link in a chain, not a call: the steps in `chains.py` compose this between
    their prompt and their parser, and name the run themselves.
    """
    return model.with_structured_output(schema, method="json_schema")


def explain(exc: Exception) -> str:
    """A transport failure, in words worth printing.

    The graph catches these per node rather than letting them escape: a single
    slow article must not take the whole batch down.
    """
    text = str(exc) or exc.__class__.__name__
    lowered = text.lower()
    if any(word in lowered for word in ("connect", "refused", "unreachable", "timed out")):
        return f"Cannot reach Ollama: {text}. Is the container up? `docker compose up -d ollama`"
    return text


def available_models(base_url: str = DEFAULT_BASE_URL, *, timeout: float = 15.0) -> list[str]:
    """Model tags Ollama has pulled, for the preflight check.

    Plain HTTP rather than a client object: this runs before anything else and
    its whole job is to produce a clear message when the container is down.
    """
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise LLMError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(_unreachable(base_url, exc.reason)) from exc
    return [model["name"] for model in payload.get("models", [])]


def _unreachable(base_url: str, reason: object) -> str:
    return (
        f"Cannot reach Ollama at {base_url}: {reason}. "
        "Is the container up? `docker compose up -d ollama`"
    )
