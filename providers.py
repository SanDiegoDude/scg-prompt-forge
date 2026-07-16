"""AI provider configuration + server-side proxy for SCG Prompt Forge.

Providers are declared in a local ``.env`` file (see ``.env.example``) using the
format::

    AI_PROVIDER_<ID> = Label | model | base_url (blank = official OpenAI) | api_key

When this plugin has no ``.env`` of its own, it falls back to the one in the
sibling ``scg_json_prompt_agent`` plugin so existing keys work with zero setup.

The browser UI never receives the base URL or API key. It only learns each
provider's id/label/model and then asks this server to perform the chat
completion on its behalf (``/scg_prompt_forge/chat``). That keeps keys on the
machine running ComfyUI and sidesteps browser CORS entirely.
"""

import os
import re
import asyncio
from urllib.parse import urlsplit

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
FALLBACK_ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "scg_json_prompt_agent", ".env",
)
DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"

# Reasoning models on the OpenAI API behave differently: they take
# ``max_completion_tokens`` (not ``max_tokens``), accept a ``reasoning_effort``
# knob, and reject custom ``temperature`` values.
_REASONING_RE = re.compile(r"^(o\d|gpt-5)", re.IGNORECASE)

# Gemini on Vertex AI is reached through its OpenAI-compatible endpoint, but it
# authenticates with a short-lived Google OAuth token (ADC or a service-account
# JSON) instead of a static key, and models must be prefixed with ``google/``.
VERTEX_SCHEME = "vertex://"
_VERTEX_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
_vertex_creds_cache = {}


def _parse_provider_line(raw_value):
    """Split ``Label | model | base_url | api_key`` into a provider dict."""
    parts = [p.strip() for p in raw_value.split("|")]
    label = parts[0] if len(parts) > 0 else ""
    model = parts[1] if len(parts) > 1 else ""
    base_url = parts[2] if len(parts) > 2 else ""
    api_key = parts[3] if len(parts) > 3 else ""
    if not base_url:
        base_url = DEFAULT_OPENAI_BASE
    return {
        "label": label or model or "Provider",
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
    }


def _parse_env(path):
    providers = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return providers
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.startswith("AI_PROVIDER_"):
            continue
        pid = key[len("AI_PROVIDER_"):].strip()
        if not pid:
            continue
        cfg = _parse_provider_line(value.strip())
        if not cfg["model"]:
            continue
        providers[pid] = cfg
    return providers


def load_providers():
    """Parse the local ``.env`` (falling back to the scg_json_prompt_agent one)
    and return an ordered dict of id -> provider config."""
    providers = _parse_env(ENV_PATH)
    if not providers:
        providers = _parse_env(FALLBACK_ENV_PATH)
    return providers


def public_providers():
    """Provider list safe to expose to the browser (no base_url / api_key)."""
    out = []
    for pid, cfg in load_providers().items():
        out.append({
            "id": pid,
            "label": cfg["label"],
            "model": cfg["model"],
            "has_key": bool(cfg["api_key"]),
        })
    return out


def _chat_completions_url(base_url):
    """Resolve the chat-completions endpoint from a configured base URL.

    Bare hosts (e.g. ``http://host:1234`` from LM Studio) get ``/v1`` added;
    URLs that already carry a version path are used as-is.
    """
    base = (base_url or DEFAULT_OPENAI_BASE).rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    path = urlsplit(base).path.strip("/")
    if path == "":
        return base + "/v1/chat/completions"
    return base + "/chat/completions"


def is_vertex(base_url):
    return bool(base_url) and base_url.strip().lower().startswith(VERTEX_SCHEME)


def _vertex_parts(base_url):
    """Parse ``vertex://PROJECT/LOCATION`` -> (project, location)."""
    rest = base_url.strip()[len(VERTEX_SCHEME):].strip("/")
    bits = [b for b in rest.split("/") if b]
    project = bits[0] if bits else ""
    location = bits[1] if len(bits) > 1 else "global"
    return project, location


def vertex_chat_url(base_url):
    project, location = _vertex_parts(base_url)
    if location == "global":
        host = "https://aiplatform.googleapis.com"
    else:
        host = "https://%s-aiplatform.googleapis.com" % location
    return "%s/v1/projects/%s/locations/%s/endpoints/openapi/chat/completions" % (
        host, project, location,
    )


def vertex_access_token(sa_path=""):
    """Return a fresh Google OAuth access token for Vertex AI.

    Uses a service-account JSON when ``sa_path`` is given, otherwise falls back
    to Application Default Credentials (``gcloud auth application-default
    login``). Raises if google-auth is missing or credentials can't be found.
    """
    from google.auth.transport.requests import Request
    key = sa_path or "__adc__"
    creds = _vertex_creds_cache.get(key)
    if creds is None:
        if sa_path:
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                sa_path, scopes=_VERTEX_SCOPES,
            )
        else:
            import google.auth
            creds, _ = google.auth.default(scopes=_VERTEX_SCOPES)
        _vertex_creds_cache[key] = creds
    if not creds.valid:
        creds.refresh(Request())
    return creds.token


def build_request_body(cfg, payload):
    """Construct the outbound OpenAI-compatible request body.

    ``payload`` is the JSON sent by the browser (messages, temperature, etc.).
    Provider model/keys come from the server-side config.
    """
    model = cfg["model"]
    vertex = is_vertex(cfg["base_url"])
    if vertex and not model.startswith("google/"):
        model = "google/" + model
    body = {
        "model": model,
        "messages": payload.get("messages", []),
        "stream": False,
    }

    try:
        max_tokens = int(payload.get("max_tokens") or 8192)
    except (TypeError, ValueError):
        max_tokens = 8192
    max_tokens = max(64, min(max_tokens, 32768))

    host = (urlsplit(cfg["base_url"]).hostname or "")
    is_openai = host.endswith("openai.com")
    is_reasoning = bool(_REASONING_RE.match((model or "").strip()))

    if is_openai and is_reasoning:
        # GPT-5 / o-series funkiness: completion-token field + reasoning effort,
        # and they reject a custom temperature, so we omit it entirely.
        body["max_completion_tokens"] = max_tokens
        body["reasoning_effort"] = "low"
    else:
        body["max_tokens"] = max_tokens
        temp = payload.get("temperature", None)
        if temp is not None:
            try:
                body["temperature"] = float(temp)
            except (TypeError, ValueError):
                pass

    rf = payload.get("response_format")
    if rf:
        body["response_format"] = rf
    return body


def register_routes():
    """Register the provider + proxy routes on the ComfyUI server."""
    try:
        from server import PromptServer
        import aiohttp
        from aiohttp import web
    except Exception:
        return

    inst = getattr(PromptServer, "instance", None)
    if inst is None:
        return
    routes = inst.routes

    @routes.get("/scg_prompt_forge/providers")
    async def _providers(request):
        return web.json_response({"providers": public_providers()})

    @routes.post("/scg_prompt_forge/chat")
    async def _chat(request):
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON body"}, status=400)

        pid = payload.get("provider_id")
        providers = load_providers()
        cfg = providers.get(pid)
        if not cfg:
            return web.json_response(
                {"error": "Unknown provider '%s'. Edit .env and Refresh." % pid},
                status=400,
            )

        body = build_request_body(cfg, payload)
        headers = {"Content-Type": "application/json"}

        if is_vertex(cfg["base_url"]):
            url = vertex_chat_url(cfg["base_url"])
            try:
                loop = asyncio.get_event_loop()
                token = await loop.run_in_executor(
                    None, vertex_access_token, cfg["api_key"] or ""
                )
            except Exception as exc:
                return web.json_response(
                    {"error": "Vertex auth failed: %s. Run `gcloud auth "
                              "application-default login` or point the 4th .env "
                              "field at a service-account JSON." % exc},
                    status=401,
                )
            headers["Authorization"] = "Bearer " + token
        else:
            url = _chat_completions_url(cfg["base_url"])
            if cfg["api_key"]:
                headers["Authorization"] = "Bearer " + cfg["api_key"]

        timeout = aiohttp.ClientTimeout(total=300)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=body, headers=headers) as resp:
                    text = await resp.text()
                    return web.Response(
                        status=resp.status,
                        text=text,
                        content_type="application/json",
                    )
        except Exception as exc:  # network error, timeout, bad host, etc.
            return web.json_response(
                {"error": "Upstream request failed: %s" % exc}, status=502
            )
