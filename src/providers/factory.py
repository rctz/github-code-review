import logging

from providers.base import LLMProvider
from providers.litellm import LiteLLMProvider
from providers.models import LiteLLMModel

logger = logging.getLogger(__name__)


class LLMFactory:
    """Provider-agnostic factory for creating LLM instances."""

    @staticmethod
    def create(
        model: LiteLLMModel = LiteLLMModel.CLAUDE_SONNET_4_6,
        temperature: float = 0.6,
    ) -> LLMProvider:
        """Create an LLM provider based on the model identifier.

        Args:
            model: Model identifier (LiteLLMModel enum value or string).
            temperature: Sampling temperature.

        Returns:
            A configured LLMProvider instance.
        """
        model_str = str(model)

        # Default: route through LiteLLM proxy (supports all configured models)
        logger.debug("Creating LiteLLM provider for model: %s", model_str)
        return LiteLLMProvider(model=model, temperature=temperature)
