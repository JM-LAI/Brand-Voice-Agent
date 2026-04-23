import requests

from app.config import AGENT_API_URL, CHAT_API_URL, BILLING_PROJECT
from app.settings import get_api_key, get_agent_token, log
from app.prompts import get_system_prompt


def call_agent(message: str) -> str:
    """Brand Voice rewrite via Lightning AI Agent conversations API."""
    token = get_agent_token()
    if not token:
        raise ValueError("Agent auth token not set — add it in Settings")

    resp = requests.post(
        AGENT_API_URL,
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        },
        json={
            "conversationId": "",
            "autoName": False,
            "stream": False,
            "billingProjectId": BILLING_PROJECT,
            "message": {
                "author": {"role": "user"},
                "content": [{"contentType": "text", "parts": [message]}],
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    # agent response shape: result.choices[0].delta.content
    try:
        content = data["result"]["choices"][0]["delta"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ValueError(f"Unexpected agent response: {data}")

    return content.strip()


def _friendly_error(err: Exception) -> str:
    """Turn raw API errors into something a human can act on."""
    msg = str(err)
    if isinstance(err, requests.exceptions.Timeout):
        return "API timed out — Lightning AI may be slow. Try again in a moment."
    if isinstance(err, requests.exceptions.ConnectionError):
        return "Can't reach Lightning AI — check your internet connection."
    if isinstance(err, requests.exceptions.HTTPError):
        code = getattr(err.response, 'status_code', None)
        if code == 401:
            return "Invalid API key — update it in Settings → API Key."
        if code == 403:
            return "API key doesn't have access — check your Lightning AI account."
        if code == 429:
            return "Rate limited — too many requests. Wait a few seconds and try again."
        if code and code >= 500:
            return f"Lightning AI server error ({code}) — try again in a moment."
        return f"API error ({code}) — {msg[:100]}"
    if "API key not set" in msg:
        return msg
    return f"Rewrite failed: {msg[:150]}"


def call_model(message: str, model: str, system_prompt: str, retries: int = 2) -> str:
    """Direct rewrite via Lightning AI chat completions API with retry on timeout."""
    api_key = get_api_key()
    if not api_key:
        raise ValueError("API key not set — add it in Settings")

    last_err = None
    for attempt in range(1 + retries):
        try:
            resp = requests.post(
                CHAT_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "temperature": 0.3,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()

            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                raise ValueError(f"Unexpected API response: {data}")

            return content.strip().lstrip("\n")

        except requests.exceptions.Timeout as e:
            last_err = e
            log(f"API timeout (attempt {attempt + 1}/{1 + retries}), retrying...")
            continue
        except Exception as e:
            raise ValueError(_friendly_error(e)) from e

    raise ValueError(_friendly_error(last_err))


def rewrite(message: str, mode: str, model: str) -> str:
    """Rewrite a message using the chat completions API with editable local rules."""
    system_prompt = get_system_prompt(mode)
    log(f"Rewriting via {model} (mode: {mode})")
    return call_model(message, model, system_prompt)
