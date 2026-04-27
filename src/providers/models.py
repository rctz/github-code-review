from enum import StrEnum


class LiteLLMModel(StrEnum):
    CLAUDE_SONNET_4_6 = "openai/claude-sonnet-4-6"
    GLM_5_1 = "openai/glm-5.1"
    GPT_5_4 = "gpt-5.4"
    KIMI_K_2_5 = "openai/kimi-k2.5"
