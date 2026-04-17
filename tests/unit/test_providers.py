from unittest.mock import patch

import pytest

from providers.base import LLMProvider
from providers.factory import LLMFactory
from providers.models import LiteLLMModel


class TestLLMProviderBase:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]


class TestLiteLLMModel:
    def test_enum_values(self) -> None:
        assert LiteLLMModel.CLAUDE_SONNET_4_6 == "openai/claude-sonnet-4-6"
        assert LiteLLMModel.GPT_5_4 == "gpt-5.4"
        assert LiteLLMModel.GLM_5_1 == "openai/glm-5.1"

    def test_str_conversion(self) -> None:
        assert str(LiteLLMModel.CLAUDE_SONNET_4_6) == "openai/claude-sonnet-4-6"


class TestLLMFactory:
    @patch("providers.factory.LiteLLMProvider")
    def test_create_returns_provider(self, mock_litellm_cls: object) -> None:
        # LiteLLMProvider.__init__ would fail without env vars,
        # so we patch the class to avoid real initialization.
        mock_instance = object()
        mock_litellm_cls.return_value = mock_instance
        provider = LLMFactory.create(model=LiteLLMModel.GPT_5_4)
        assert provider is mock_instance

    @patch("providers.factory.LiteLLMProvider")
    def test_create_with_string_model(self, mock_litellm_cls: object) -> None:
        mock_instance = object()
        mock_litellm_cls.return_value = mock_instance
        provider = LLMFactory.create(model="gpt-5.4")
        assert provider is mock_instance

    @patch("providers.factory.LiteLLMProvider")
    def test_create_passes_temperature(self, mock_litellm_cls: object) -> None:
        mock_instance = object()
        mock_litellm_cls.return_value = mock_instance
        LLMFactory.create(model=LiteLLMModel.CLAUDE_SONNET_4_6, temperature=0.9)
        mock_litellm_cls.assert_called_once_with(model=LiteLLMModel.CLAUDE_SONNET_4_6, temperature=0.9)
