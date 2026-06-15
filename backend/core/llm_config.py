"""Single place to configure the LLM provider — edit backend/.env ONLY.

Point the app at any OpenAI-compatible provider/proxy by setting four values in
backend/.env (no code changes):

    PROXY_URL       the provider/proxy endpoint
    MODEL           the model id to call
    API_KEY         your key for that provider
    USE_MOCK_LLM    true to run offline with canned content (no key/network)

Values are read at call time, so editing .env + restarting the server is all that's
needed. Secrets stay in .env — never hardcode the key in a committed file.

PROXY_URL may be either the base URL (e.g. ".../v1") or the full chat-completions
endpoint (".../v1/chat/completions"). A trailing "/chat/completions" is stripped
automatically, because the OpenAI SDK appends that path itself.

--- PROVIDER EXAMPLES (put these in backend/.env) ----------------------------
# OpenRouter — https://openrouter.ai  (keys: https://openrouter.ai/keys)
#   PROXY_URL=https://openrouter.ai/api/v1
#   MODEL=google/gemini-2.5-flash-lite     (or e.g. openai/gpt-5.4-mini,
#                                           meta-llama/llama-3.3-70b-instruct)
#   API_KEY=sk-or-...
#
# Chutes — https://chutes.ai  (list models: GET https://llm.chutes.ai/v1/models)
#   PROXY_URL=https://llm.chutes.ai/v1
#   MODEL=<a model id from the list above>
#   API_KEY=cpk_...
#
# Tip: a router like OpenRouter is the easiest target — it accepts `max_tokens`
# and `temperature` for every model. Pointing PROXY_URL straight at OpenAI's
# native API with one of their reasoning models would need a small llm.py tweak
# (they require `max_completion_tokens` and reject `temperature`).
"""

import os

# Sensible defaults so nothing breaks if the vars are unset.
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


def use_mock():
    """True when USE_MOCK_LLM is truthy — return canned content, no network."""
    return os.getenv("USE_MOCK_LLM", "false").strip().lower() in ("1", "true", "yes", "on")


def get_base_url():
    """Base URL for the OpenAI SDK, derived from PROXY_URL.

    The OpenAI client appends '/chat/completions' itself, so if PROXY_URL is given
    as the full endpoint we strip that suffix to get the base it expects.
    """
    url = (os.getenv("PROXY_URL") or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    url = url.rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    return url


def get_api_key():
    """The provider API key from .env."""
    return (os.getenv("API_KEY") or "").strip()


def get_model():
    """The model id to call, from .env (falls back to a default)."""
    return (os.getenv("MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
