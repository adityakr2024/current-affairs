import os

PROVIDERS: dict[str, dict] = {

    # ── Groq — best free reasoning ────────────────────────────────────────────
    "groq_1": {
        "type": "groq", "key_env": "GROQ_API_KEY_1",
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1",
        "rpm": 30, "tpm": 6000, "tpd": 14400, "priority": 1,
        "tasks": ["enrich", "oneliner", "caption"],  # FIX: added oneliner+caption fallback
        "enabled": True,
    },
    "groq_2": {
        "type": "groq", "key_env": "GROQ_API_KEY_2",
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1",
        "rpm": 30, "tpm": 6000, "tpd": 14400, "priority": 1,
        "tasks": ["enrich", "oneliner", "caption"],  # FIX: added oneliner+caption fallback
        "enabled": True,
    },
    "groq_3": {
        "type": "groq", "key_env": "GROQ_API_KEY_3",
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1",
        "rpm": 30, "tpm": 6000, "tpd": 14400, "priority": 1,
        "tasks": ["enrich", "oneliner", "caption"],  # FIX: added oneliner+caption fallback
        "enabled": True,
    },
    "groq_4": {
         "type": "groq", "key_env": "GROQ_API_KEY_4",
         "model": "llama-3.3-70b-versatile",
         "base_url": "https://api.groq.com/openai/v1",
         "rpm": 30, "tpm": 6000, "tpd": 14400, "priority": 1,
         "tasks": ["enrich", "oneliner", "caption"],  # FIX: added oneliner+caption fallback
         "enabled": True,
    },

    # ── Cerebras — fast 70b ───────────────────────────────────────────────────
    "cerebras_1": {
        "type": "openai_compat", "key_env": "CEREBRAS_API_KEY_1",
        "model": "llama-3.3-70b",                   # FIX: was llama3.1-70b (404)
        "base_url": "https://api.cerebras.ai/v1",
        "rpm": 30, "tpm": 60000, "tpd": 0, "priority": 2,
        "tasks": ["enrich"], "enabled": True,
    },

    # ── Gemini Flash — light tasks ────────────────────────────────────────────
    "gemini_1": {
        "type": "google", "key_env": "GEMINI_API_KEY_1",
        "model": "gemini-2.0-flash-lite",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "rpm": 30, "tpm": 0, "tpd": 1500, "priority": 1,
        "tasks": ["oneliner", "caption", "filter"], "enabled": True,
    },
    "gemini_2": {
        "type": "google", "key_env": "GEMINI_API_KEY_2",
        "model": "gemini-2.0-flash-lite",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "rpm": 30, "tpm": 0, "tpd": 1500, "priority": 1,
        "tasks": ["oneliner", "caption", "filter"], "enabled": True,
    },
    "gemini_3": {
        "type": "google", "key_env": "GEMINI_API_KEY_3",
        "model": "gemini-2.0-flash-lite",            # FIX: was gemini-1.5-flash (404)
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "rpm": 15, "tpm": 0, "tpd": 1500, "priority": 2,
        "tasks": ["oneliner", "caption", "filter"], "enabled": True,
    },

    # ── OpenAI ────────────────────────────────────────────────────────────────
    "openai_1": {
        "type": "openai_compat", "key_env": "OPENAI_API_KEY_1",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "rpm": 500, "tpm": 200000, "tpd": 0, "priority": 2,
        "tasks": ["enrich", "oneliner", "caption"], "enabled": True,
    },
    "openai_2": {
        "type": "openai_compat", "key_env": "OPENAI_API_KEY_2",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "rpm": 500, "tpm": 200000, "tpd": 0, "priority": 2,
        "tasks": ["enrich", "oneliner", "caption"], "enabled": True,
    },
    "openai_3": {
        "type": "openai_compat", "key_env": "OPENAI_API_KEY_3",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "rpm": 500, "tpm": 200000, "tpd": 0, "priority": 2,
        "tasks": ["enrich", "oneliner", "caption"], "enabled": True,
    },

    # ── OpenRouter — light fallback ───────────────────────────────────────────
    "openrouter_1": {
        "type": "openai_compat", "key_env": "OPENROUTER_API_KEY_1",
        "model": "meta-llama/llama-3.2-3b-instruct:free",
        "base_url": "https://openrouter.ai/api/v1",
        "rpm": 20, "tpm": 0, "tpd": 0, "priority": 3,
        "tasks": ["oneliner", "caption"], "enabled": True,
    },
    "openrouter_2": {
        "type": "openai_compat", "key_env": "OPENROUTER_API_KEY_2",
        "model": "meta-llama/llama-3.2-3b-instruct:free",
        "base_url": "https://openrouter.ai/api/v1",
        "rpm": 20, "tpm": 0, "tpd": 0, "priority": 3,
        "tasks": ["oneliner", "caption"], "enabled": True,
    },

    # ── Anthropic — paid, highest quality, enrich fallback ───────────────────
    "claude_1": {
        "type": "anthropic", "key_env": "ANTHROPIC_API_KEY_1",
        "model": "claude-haiku-4-5-20251001",
        "base_url": "https://api.anthropic.com/v1",
        "rpm": 50, "tpm": 0, "tpd": 0, "priority": 4,
        "tasks": ["enrich"], "enabled": True,
    },
}


def get_api_key(provider_name: str) -> str | None:
    spec = PROVIDERS.get(provider_name)
    return os.environ.get(spec["key_env"], "") if spec else None


def active_providers(task: str | None = None) -> list[str]:
    """
    Return enabled providers with a key present, filtered by task.

    SINGLE-KEY FALLBACK: if only one provider is active total, it is returned
    for ALL tasks regardless of its tasks spec — so the system always runs.
    """
    all_active = [
        name for name, spec in PROVIDERS.items()
        if spec.get("enabled", True) and os.environ.get(spec["key_env"], "")
    ]
    all_active.sort(key=lambda n: (PROVIDERS[n].get("priority", 5), n))

    # Single-provider mode: use the one provider for everything
    if len(all_active) <= 1:
        return all_active

    if not task:
        return all_active

    task_filtered = [
        name for name in all_active
        if not PROVIDERS[name].get("tasks") or task in PROVIDERS[name].get("tasks", [])
    ]

    # If no provider matches this specific task, fall back to any available provider
    return task_filtered if task_filtered else all_active
