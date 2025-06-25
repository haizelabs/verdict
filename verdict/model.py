import pprint
import textwrap
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    ContextManager,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
    Union,
)

from loguru._logger import Logger
from typing_extensions import Self

from verdict.schema import Schema
from verdict.util.exceptions import ConfigurationError
from verdict.util.misc import DisableLogger, shorten_string
from verdict.util.ratelimit import (
    RateLimitConfig,
    RateLimitPolicy,
    UnlimitedRateLimiter,
)


class Model(ABC):
    name: str
    use_nonce: bool = False  # Default value for the base class

    rate_limiter: Optional[Union[RateLimitPolicy, RateLimitConfig]] = field(
        repr=False, default=None
    )
    rate_limit: RateLimitPolicy = field(init=False, repr=True)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", self.name.split("/")[0])

    def _configure_rate_limiter(self) -> None:
        from verdict import config

        if config.state.rate_limiter_disabled:
            rate_limit = RateLimitPolicy(
                {
                    UnlimitedRateLimiter(): "requests",
                }
            )
        elif self.rate_limiter is None:
            rate_limit = config.DEFAULT_RATE_LIMITER
        elif isinstance(self.rate_limiter, dict):
            rate_limit = RateLimitPolicy(self.rate_limiter)
        elif isinstance(self.rate_limiter, RateLimitPolicy):
            rate_limit = self.rate_limiter
        else:
            raise ConfigurationError(
                "Invalid rate_limiter passed. Must be a RateLimit or a dictionary of RateLimiters -> metric"
            )

        object.__setattr__(self, "rate_limit", rate_limit)

    @property
    def char(self) -> str:
        return self.name.split("/")[-1]

    def __str__(self) -> str:
        components = self.name.split("/")
        if len(components) == 1:
            return f"{self.__class__.__name__}({self.name})"
        return f"{self.__class__.__name__}(.../{components[-1]})"

    @property
    def connection_parameters(self) -> dict[str, Any]:
        return {
            "num_retries": 1,  # NOTE: this overrides litellm's retry mechanism so we can control it with ModelSelectionPolicy
            "max_retries": 1,  # NOTE: ditto, but for instructor
        }


@dataclass(frozen=True)
class ProviderModel(Model):
    name: str
    use_nonce: bool = False

    rate_limiter: Optional[Union[RateLimitPolicy, RateLimitConfig]] = field(
        repr=False, default=None
    )
    rate_limit: RateLimitPolicy = field(init=False, repr=True)

    def __post_init__(self) -> None:
        super().__post_init__()

        object.__setattr__(self, "use_nonce", True)

        from litellm import get_llm_provider  # type: ignore[import-untyped]

        _, provider, _, _ = get_llm_provider(self.name)
        object.__setattr__(self, "provider", provider)

        from verdict import config

        if self.rate_limiter is None:
            rate_limiter = config.PROVIDER_RATE_LIMITER.get(
                provider, config.DEFAULT_RATE_LIMITER
            )
            object.__setattr__(self, "rate_limiter", rate_limiter)

        self._configure_rate_limiter()

    @property
    def connection_parameters(self) -> dict[str, Any]:
        from verdict import config

        return {
            "model": self.name,
            "timeout": config.DEFAULT_PROVIDER_TIMEOUT,  # NOTE: this can be overridden by the inference_parameters passed to the Client
            "stream_timeout": config.DEFAULT_PROVIDER_STREAM_TIMEOUT,  # NOTE: this is set to `timeout` if streaming is True
            **super().connection_parameters,
        }


@dataclass(frozen=True)
class vLLMModel(Model):
    name: str
    api_base: str
    api_key: str
    use_nonce: bool = field(init=False)

    rate_limiter: Optional[Union[RateLimitPolicy, RateLimitConfig]] = field(
        repr=False, default=None
    )
    rate_limit: RateLimitPolicy = field(init=False, repr=True)

    def __post_init__(self) -> None:
        super().__post_init__()

        object.__setattr__(self, "use_nonce", False)
        self._configure_rate_limiter()

    @property
    def connection_parameters(self) -> dict[str, Any]:
        return {
            "model": f"hosted_vllm/{self.name}",
            "api_base": self.api_base,
            "api_key": self.api_key,
            "timeout": None,  # NOTE: this can be overridden by the inference_parameters passed to the Client
            "stream_timeout": None,  # NOTE: this is set to `timeout` if streaming is True
            **super().connection_parameters,
        }


@dataclass
class Client:
    complete: Callable
    model: Model
    inference_parameters: dict[str, Any]

    def _supports_image_input(self) -> bool:
        if hasattr(self.model, "provider"):
            # TODO: add more model providers
            VISION_MODELS = {
                "openai": [
                    "o4-mini",
                    "o3",
                    "o3-pro",
                    "o1",
                    "o1-pro",
                    "gpt-4.1",
                    "gpt-4o",
                    "chatgpt-4o-latest",
                    "gpt-4.1-mini",
                    "o4-mini",
                    "gpt-4.1-nano",
                    "gpt-4o-mini",
                ],
            }

            provider_models = VISION_MODELS.get(self.model.provider, [])
            return self.model.char in provider_models
        return False

    def _has_image_content(
        self, messages: List[Dict[str, str | List[Dict[str, str | Dict[str, str]]]]]
    ) -> bool:
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        return True

        return False

    @contextmanager
    def defaults(self, **inference_parameters_defaults) -> ContextManager[None]:  # type: ignore
        original_inference_parameters = self.inference_parameters

        self.inference_parameters = {
            **inference_parameters_defaults,
            **original_inference_parameters,
        }
        yield

        self.inference_parameters = original_inference_parameters

    def __call__(
        self,
        logger: Logger,
        messages: List[Dict[str, str]],
        response_model: Optional[Schema] = None,
        streaming: bool = False,
    ):
        from verdict import config

        if self._has_image_content(messages) and not self._supports_image_input():
            raise ConfigurationError(
                f"Model {self.model.name} does not support image inputs. "
                f"Images were detected in the message content. "
            )

        logger.debug(
            textwrap.dedent(
                f"""
                Preparing parameters for {repr(self.model)} with
                specified connection_parameters: {self.model.connection_parameters}
                default inference_parameters: {config.DEFAULT_INFERENCE_PARAMS}
                specified inference_parameters: {self.inference_parameters}
                """
            )
        )

        # 1. add in messages, connection_parameters, and inference_parameters (defaults first)
        parameters = {
            "messages": messages,
            **self.model.connection_parameters,
            **config.DEFAULT_INFERENCE_PARAMS,
            **self.inference_parameters,
        }

        # 2. configure streaming
        if streaming:
            parameters["stream"] = streaming
            if response_model is not None:
                # needed for streaming structured output
                from instructor import Partial  # type: ignore[import-untyped]

                response_model = Partial[response_model]
            if "timeout" in self.inference_parameters:
                parameters["stream_timeout"] = self.inference_parameters["timeout"]

        # 3. configure structured output
        if response_model is not None:
            parameters["response_model"] = response_model

        parameters_no_api_key = {
            p: v for p, v in parameters.items() if p not in ["api_key"]
        }
        logger.debug(
            f"Sending parameters for {repr(self.model)}:  {pprint.pformat(parameters_no_api_key, width=80, depth=3)}"
        )
        return self.complete(**parameters)


class ClientWrapper:
    model: Model
    inference_parameters: dict[str, Any]

    def __init__(self, model: Model, **inference_parameters) -> None:
        self.model = model
        self.model._configure_rate_limiter()

        self.inference_parameters = inference_parameters

        import litellm

        litellm.drop_params = True
        litellm.suppress_debug_info = True
        self.raw_client = Client(
            litellm.LiteLLM().chat.completions.create,
            self.model,
            self.inference_parameters,
        )

        from instructor import Mode, patch  # type: ignore[import-untyped]

        MODEL_PROVIDER_TO_INSTRUCTOR_MODE_OVERRIDE = {
            "huggingface": Mode.JSON,
            "deepinfra": Mode.JSON,
            "together_ai": Mode.JSON,
        }

        MODEL_TO_INSTRUCTOR_MODE_OVERRIDE = {
            "openai/o1": Mode.JSON_O1,
            "openai/o1-2024-12-17": Mode.JSON_O1,
        }

        with DisableLogger("LiteLLM"):
            self.function_calling_client = Client(
                patch(
                    litellm.LiteLLM(),
                    mode=MODEL_TO_INSTRUCTOR_MODE_OVERRIDE.get(
                        f"{self.model.provider}/{self.model.char}",
                        MODEL_PROVIDER_TO_INSTRUCTOR_MODE_OVERRIDE.get(
                            self.model.provider, Mode.TOOLS
                        ),
                    ),
                ).chat.completions.create,  # type: ignore
                self.model,
                self.inference_parameters,
            )

    def encode(self, word: str) -> List[int]:
        import tokenizers  # type: ignore[import-untyped]
        from litellm import encode  # type: ignore[import-untyped]

        tokens = encode(model=self.model.name, text=shorten_string(word, encoded=False))
        if isinstance(tokens, tokenizers.Encoding):
            return tokens.ids

        return tokens

    @staticmethod
    def from_model(model: Model, **inference_parameters) -> "ClientWrapper":
        return ClientWrapper(model, **inference_parameters)


class ModelSelectionPolicy:
    @property
    def char(self) -> str:
        return str(self)

    def __init__(self) -> None:
        self.client_factories: List[Callable[[], ClientWrapper]] = []
        self.client_configs: List[Tuple[Model, int, dict]] = []
        self.client_repeats: List[Tuple[Model, int]] = []

    def __len__(self) -> int:
        return len(self.client_factories)

    def get_clients(self) -> Iterator[ClientWrapper]:
        return iter(map(lambda factory: factory(), self.client_factories))

    @staticmethod
    def from_name(
        model: Union[str, Model], retries: int = 1, **inference_parameters
    ) -> "ModelSelectionPolicy":
        policy = ModelSelectionPolicy()
        for _ in range(retries):
            if isinstance(model, str):
                model = ProviderModel(name=model)

            policy.client_factories.append(
                lambda: ClientWrapper.from_model(model, **inference_parameters)
            )
            policy.client_configs.append((model, retries, inference_parameters))
        policy.client_repeats.append((model, retries))

        return policy

    @staticmethod
    def from_names(model_names: List[Tuple[str, int, dict]]) -> "ModelSelectionPolicy":
        policy = ModelSelectionPolicy()
        for model_name, retries, inference_parameters in model_names:
            policy += ModelSelectionPolicy.from_name(
                model_name, retries, **inference_parameters
            )

        return policy

    @staticmethod
    def from_any(
        policy_or_name: Union[
            "ModelSelectionPolicy", str, Model, List[Union[str, Model]]
        ],
        retries: int = 1,
        **inference_parameters,
    ) -> "ModelSelectionPolicy":
        if isinstance(policy_or_name, ModelSelectionPolicy):
            return policy_or_name
        elif isinstance(policy_or_name, (str, Model)):
            return ModelSelectionPolicy.from_name(
                policy_or_name, retries, **inference_parameters
            )
        elif isinstance(policy_or_name, list) and len(policy_or_name) > 0:
            if isinstance(policy_or_name[0], (str, Model)):
                return ModelSelectionPolicy.from_names(
                    [(name, retries, inference_parameters) for name in policy_or_name]
                )
            elif isinstance(policy_or_name[0], tuple):
                return ModelSelectionPolicy.from_names(policy_or_name)
            else:
                raise ConfigurationError(
                    "Invalid argument type. Expected str, list, or ModelSelectionPolicy."
                )
        else:
            raise ConfigurationError(
                "Invalid argument type. Expected str, list, or ModelSelectionPolicy."
            )

    def __add__(self, other: "ModelSelectionPolicy") -> Self:
        self.client_factories.extend(other.client_factories)
        self.client_configs.extend(other.client_configs)
        self.client_repeats.extend(other.client_repeats)
        return self

    def __str__(self) -> str:
        return ", ".join(
            f"{retries}x {model.name}" for model, retries in self.client_repeats
        )

    def __repr__(self) -> str:
        return self.__str__()


class ModelConfigurable(ABC):
    _model_selection_policy: Optional[ModelSelectionPolicy] = None

    def via(
        self,
        policy_or_name: Union[
            ModelSelectionPolicy, str, Model, List[Union[str, Model]]
        ],
        retries: int = 1,
        **inference_parameters,
    ) -> Self:
        self.set(
            "model_selection_policy",
            ModelSelectionPolicy.from_any(
                policy_or_name, retries, **inference_parameters
            ),
        )
        return self

    # provided by Node, Graph
    @abstractmethod
    def set(self, attr, value) -> None:
        pass

    @property
    def model_selection_policy(self) -> Optional[ModelSelectionPolicy]:
        return self._model_selection_policy

    @model_selection_policy.setter
    def model_selection_policy(
        self, model_selection_policy: ModelSelectionPolicy
    ) -> None:
        from verdict.util.log import logger

        # only set the model selection policy if it hasn't been set yet
        if self._model_selection_policy is None:
            self._model_selection_policy = model_selection_policy
            logger.info(f"Model selection policy set to {model_selection_policy.char}")
        else:
            logger.warning("Model selection policy skipped. Already set.")
            pass
