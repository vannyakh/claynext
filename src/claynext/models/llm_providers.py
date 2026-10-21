"""Cloud LLM platforms that speak the OpenAI chat API."""
from __future__ import annotations

# Order is the auto-translate fallback after Gemini. Each entry is one stored key provider.
CHAT_PROVIDERS: dict[str, dict] = {
    "qwen": {
        "label": "Qwen",
        "env": ("DASHSCOPE_API_KEY", "QWEN_API_KEY"),
        "base": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "rpm": 60,
        "rpd": 10000,
    },
    "deepseek": {
        "label": "DeepSeek",
        "env": ("DEEPSEEK_API_KEY",),
        "base": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "rpm": 60,
        "rpd": 10000,
    },
    "groq": {
        "label": "Groq",
        "env": ("GROQ_API_KEY",),
        "base": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "rpm": 30,
        "rpd": 10000,
    },
    "openrouter": {
        "label": "OpenRouter",
        "env": ("OPENROUTER_API_KEY",),
        "base": "https://openrouter.ai/api/v1",
        "model": "deepseek/deepseek-chat",
        "rpm": 60,
        "rpd": 10000,
    },
    "openai": {
        "label": "OpenAI",
        "env": ("OPENAI_API_KEY",),
        "base": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "rpm": 60,
        "rpd": 10000,
    },
    "mistral": {
        "label": "Mistral",
        "env": ("MISTRAL_API_KEY",),
        "base": "https://api.mistral.ai/v1",
        "model": "mistral-small-latest",
        "rpm": 60,
        "rpd": 10000,
    },
    "moonshot": {
        "label": "Moonshot",
        "env": ("MOONSHOT_API_KEY",),
        "base": "https://api.moonshot.ai/v1",
        "model": "moonshot-v1-8k",
        "rpm": 20,
        "rpd": 5000,
    },
    "glm": {
        "label": "GLM",
        "env": ("ZHIPU_API_KEY",),
        "base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "rpm": 60,
        "rpd": 10000,
    },
    "xai": {
        "label": "xAI",
        "env": ("XAI_API_KEY",),
        "base": "https://api.x.ai/v1",
        "model": "grok-3-mini",
        "rpm": 60,
        "rpd": 10000,
    },
}

CHAT_ORDER = tuple(CHAT_PROVIDERS)


def provider_hint(provider: str) -> str:
    """One line under the add-key form: model and the speed the pool holds."""
    if provider == "gemini":
        return "Gemini free tier · 15 RPM / 1,500 RPD · keys rotate on the limit."
    spec = CHAT_PROVIDERS.get(provider)
    if not spec:
        return "Stored for this provider. Keys rotate when a call is rate limited."
    return f"{spec['label']} · {spec['model']} · {spec['rpm']} RPM · keys rotate before the limit."
