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


def call_model(message: str, model: str, system_prompt: str) -> str:
    """Direct rewrite via Lightning AI chat completions API."""
    api_key = get_api_key()
    if not api_key:
        raise ValueError("API key not set — add it in Settings")

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
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ValueError(f"Unexpected API response: {data}")

    # strip leading newlines (nemotron quirk) and whitespace
    return content.strip().lstrip("\n")


def rewrite(message: str, mode: str, model: str) -> str:
    """Rewrite a message using the chat completions API with editable local rules."""
    system_prompt = get_system_prompt(mode)
    log(f"Rewriting via {model} (mode: {mode})")
    return call_model(message, model, system_prompt)
