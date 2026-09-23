"""Thin Gemini adapter for the workout-generation pipeline.

The pipeline never depends on Google's client directly: it depends on the
:data:`~cycloai.generator.generate.ModelClient` callable (``str -> str`` —
prompt text in, raw model text out). Tests inject a fake; only a live run
constructs :class:`GeminiGeneratorClient`. This adapter stays deliberately
thin: JSON parsing, validation and the one findings-aware retry all belong
to the pipeline (:mod:`cycloai.generator.generate`) and are NOT duplicated
here.

The adapter only guarantees two things:

* The reply is requested as JSON (``response_mime_type="application/json"``)
  because the pipeline parses the raw text as JSON.
* The API key is resolved from the SAME settings the embedder uses
  (:class:`~cycloai.rag.embeddings.EmbedderSettings`): process environment
  first, then the module-anchored ``backend/.env``. It is never hardcoded,
  never logged, and no error raised by this module includes it.

Import safety: importing this module performs no network call and requires
no API key. Only constructing :class:`GeminiGeneratorClient` resolves the
key (and raises a clear, actionable error when it is missing), so the API
layer can be imported in tests without credentials.

Model choice: ``gemini-2.5-flash`` by default — fast and inexpensive, which
suits a prompt → JSON → validate → one-retry loop — configurable through
``GEMINI_GENERATION_MODEL`` (environment first, then ``backend/.env``),
mirroring how the rest of the project handles configuration.
"""

from __future__ import annotations

from google import genai
from google.genai import types

from cycloai.rag.embeddings import EmbedderSettings

__all__ = ["GeminiGeneratorClient"]


class GeminiGeneratorClient:
    """Implements the pipeline's ``ModelClient`` contract with live Gemini.

    Construction resolves the API key and may touch the network through the
    SDK; importing this module does neither.
    """

    def __init__(self, api_key: str | None = None) -> None:
        settings = EmbedderSettings()
        resolved = api_key if api_key is not None else settings.google_api_key
        if not resolved:
            raise RuntimeError(
                "GOOGLE_GENERATIVE_AI_API_KEY is not configured (process environment "
                "or backend/.env). Export it before generating workouts; it is never "
                "hardcoded and never printed."
            )
        self.api_key = resolved
        self.model = settings.generation_model
        self._client = genai.Client(api_key=resolved)

    async def __call__(self, prompt: str) -> str:
        """Return the model's raw text reply for the pipeline to parse."""
        response = await self._client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        if not response.text:
            # Never include the request or key in the error; only the outcome.
            raise RuntimeError(
                f"Gemini returned an empty response for model {self.model!r}"
            )
        return response.text
