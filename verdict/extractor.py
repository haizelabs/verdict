import math
import random
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple, Type, Union

from loguru._logger import Logger
from pydantic import BaseModel
from typing_extensions import Self

from verdict import config
from verdict.model import ClientWrapper, Model, ModelSelectionPolicy
from verdict.prompt import PromptMessage
from verdict.scale import DiscreteScale
from verdict.schema import Schema
from verdict.util.exceptions import ConfigurationError, VerdictExecutionTimeError


@dataclass
class Usage:
    in_tokens: int
    out_tokens: int

    @staticmethod
    def unknown() -> "Usage":
        return Usage(in_tokens=-1, out_tokens=-1)

    def is_unknown(self) -> bool:
        return self.in_tokens == -1 and self.out_tokens == -1


class Extractor(ABC):
    """
    Represents a method of extracting a ResponseSchema from a provider call.

    Some examples:
        1. function-calling / structured output via `instructor`
        2. obtaining probability using logprobs on some token support (eg, `yes`, `no`)
        3. having a second LLM extract from a raw response string
    """

    response_schema: Type[Schema]
    streaming: bool = False

    @abstractmethod
    def extract(
        self,
        client_wrapper: ClientWrapper,
        prompt_message: PromptMessage,
        logger: Logger,
    ) -> Tuple[Union[Schema, Iterator[Schema]], Usage]:
        pass

    def inject(self, unit) -> None:
        self.response_schema = unit.ResponseSchema
        if hasattr(unit, "scale"):
            self.scale = unit.scale
        self.streaming = getattr(unit, "should_stream_output", False)

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(streaming={self.streaming}, response_schema={self.response_schema.model_fields})"

    def __repr__(self) -> str:
        return self.__str__()

    @classmethod
    def format(cls) -> str:
        return f"{cls.__name__.replace('Extractor', '')}({{model_name}})"


class StructuredOutputExtractor(Extractor):
    def extract(
        self,
        client_wrapper: ClientWrapper,
        prompt_message: PromptMessage,
        logger: Logger,
    ) -> Tuple[Union[Schema, Iterator[Schema]], Usage]:
        assert getattr(self, "response_schema") is not None, (
            "StructuredOutputExtractor.response_schema must be set before calling extract()"
        )
        response = client_wrapper.function_calling_client(
            logger=logger,
            messages=(
                messages := prompt_message.to_messages(
                    add_nonce=client_wrapper.model.use_nonce
                )
            ),
            response_model=self.response_schema,
            streaming=self.streaming,
        )

        # TODO: add support / ping LiteLLM for image token usage tracking
        in_tokens = 0
        for message in messages:
            for content in message["content"]:
                if isinstance(content, str):
                    continue
                if content["type"] == "text":
                    in_tokens += len(client_wrapper.encode(content["text"]))

        usage = Usage(
            in_tokens=in_tokens,
            out_tokens=len(client_wrapper.encode(str(response.model_dump())))
            if not self.streaming
            else -1,
        )

        return response, usage


class RawExtractor(Extractor):
    field_name: str

    def inject(self, unit) -> None:
        super().inject(unit)

        model_fields = self.response_schema.model_fields
        assert len(model_fields) == 1, (
            "RawExtractor only supports a single output field"
        )

        [(self.field_name, field_info)] = model_fields.items()
        assert field_info.annotation is str, (
            "RawExtractor only supports a single `str` output field"
        )

    def extract(
        self,
        client_wrapper: ClientWrapper,
        prompt_message: PromptMessage,
        logger: Logger,
    ) -> Tuple[Union[Schema, Iterator[Schema]], Usage]:
        output = client_wrapper.raw_client(
            logger=logger,
            messages=(
                messages := prompt_message.to_messages(
                    add_nonce=client_wrapper.model.use_nonce
                )
            ),
            streaming=self.streaming,
        )

        def streaming_extract(output, messages) -> Iterator[Schema]:
            from litellm import stream_chunk_builder  # type: ignore[import-untyped]

            chunks = []
            for chunk in output:
                chunks.append(chunk)
                yield self.response_schema(
                    **{
                        self.field_name: stream_chunk_builder(chunks, messages=messages)
                        .choices[0]
                        .message.content
                    }
                )  # type: ignore

        if isinstance(output, Iterator):
            return streaming_extract(output, messages), Usage.unknown()
        else:
            usage = Usage(
                in_tokens=output.usage.prompt_tokens,
                out_tokens=output.usage.completion_tokens,
            )

            return self.response_schema(
                **{self.field_name: output.choices[0].message.content}
            ), usage


class CustomExtractor(RawExtractor, ABC):
    def inject(self, unit) -> None:
        Extractor.inject(self, unit)
        self.streaming = False

        self.original_response_schema = self.response_schema

        self.field_name = "output"
        self.response_schema = Schema.inline(**{self.field_name: str})

    @abstractmethod
    def post_extract(self, output: str, logger: Logger) -> Dict[str, Any]:
        pass

    def extract(
        self,
        client_wrapper: ClientWrapper,
        prompt_message: PromptMessage,
        logger: Logger,
    ) -> Tuple[Schema, Usage]:
        output, usage = super().extract(client_wrapper, prompt_message, logger)
        logger.debug(
            f"CustomExtractor {self.__class__.__name__} received output: {output.escape()}"
        )

        extracted = self.post_extract(output.output, logger)  # type: ignore
        logger.debug(
            f"CustomExtractor {self.__class__.__name__} completed post_extract: {extracted}"
        )
        if missing := set(self.original_response_schema.model_fields.keys()) - set(
            extracted.keys()
        ):
            raise ConfigurationError(
                f"Missing field(s) {missing} in CustomExtractor {self.__class__.__name__}."
            )

        try:
            return self.original_response_schema(**extracted), usage
        except Exception as e:
            raise ConfigurationError(
                f"CustomExtractor {self.__class__.__name__}.extract() failed to cast match '{extracted}' for field '{self.field_name}' in the output to {self.original_response_schema}. "
            ) from e


class RegexExtractor(CustomExtractor):
    fields: Dict[str, re.Pattern]

    FIRST_INT = r"[+-]?\d+"
    FIRST_FLOAT = r"[+-]?\d+(\.\d+)?"

    def __init__(self, fields: Dict[str, str]) -> None:
        self.fields = {field: re.compile(pattern) for field, pattern in fields.items()}

    def post_extract(self, output: str, logger: Logger) -> Dict[str, Any]:
        matches: Dict[str, Any] = {}
        for field in self.original_response_schema.model_fields.keys():
            match = (pattern := self.fields[field]).search(output)
            if match:
                match_str = match.group()
                logger.debug(
                    f"Found match {match_str} for field '{field}' with pattern '{pattern}'"
                )
                _type: Optional[Type] = self.original_response_schema.model_fields[
                    field
                ].annotation
                if _type is None:
                    raise ConfigurationError(
                        f"RegexExtractor.extract() failed to find a type for field '{field}'. Check ResponseSchema."
                    )
                logger.debug(f"Found type {_type} for field '{field}'")

                try:
                    matches[field] = _type(match_str)
                    logger.debug(f"Casted {match_str} to {_type}")
                except Exception as e:
                    raise VerdictExecutionTimeError(
                        f"RegexExtractor.extract() failed to cast match '{match_str}' for field '{field}' with pattern '{pattern}' in the output to {_type}. "
                    ) from e
            else:
                raise VerdictExecutionTimeError(
                    f"RegexExtractor.extract() failed to find a match for field '{field}' with pattern '{pattern}' in the output"
                )

        return matches

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(streaming={self.streaming}, response_schema={self.response_schema.model_fields}, fields={self.fields})"


class PostHocExtractor(StructuredOutputExtractor):
    model_selection_policy: Optional[ModelSelectionPolicy] = None
    extract_client_wrappers: Optional[List[ClientWrapper]] = None

    def __init__(
        self,
        policy_or_name: Optional[Union[str, Model, List[Union[str, Model]]]] = None,
        retries: int = 1,
        **inference_parameters,
    ) -> None:
        if policy_or_name is not None:
            self.model_selection_policy = ModelSelectionPolicy.from_any(
                policy_or_name, retries, **inference_parameters
            )
            self.extract_client_wrappers = list(
                self.model_selection_policy.get_clients()
            )

        # NOTE: could make this portion stream too, but this makes the .execute code more complex
        self.raw_extractor = RawExtractor()
        super().__init__()

    def extract(
        self,
        client_wrapper: ClientWrapper,
        prompt_message: PromptMessage,
        logger: Logger,
    ) -> Tuple[Union[Schema, Iterator[Schema]], Usage]:
        self.raw_extractor.field_name = "output"
        self.raw_extractor.response_schema = Schema.inline(output=str)
        raw_response, raw_usage = self.raw_extractor.extract(
            client_wrapper, prompt_message, logger
        )

        if self.extract_client_wrappers is not None:
            logger.debug("Using custom post-hoc clients for extraction")
            extract_client_wrappers = self.extract_client_wrappers
        else:
            logger.debug("Using same client for extraction")
            extract_client_wrappers = [client_wrapper]

        for attempt_num, extract_client_wrapper in enumerate(extract_client_wrappers):
            logger.info(
                f"Starting attempt {attempt_num + 1} of {len(extract_client_wrappers)}"
            )

            ready = extract_client_wrapper.model.rate_limit.acquire(
                {
                    "requests": 1,
                    "tokens": raw_usage.in_tokens
                    + 20,  # estimate of the additional prompt below
                }
            )
            ready.wait()
            logger.debug(f"Acquired rate limit for {extract_client_wrapper.model}")

            try:
                response, usage = super().extract(
                    extract_client_wrapper,
                    PromptMessage(
                        system="You are an expert at extracting structured data from raw text. You faithfully use ONLY the Schema function/tool.",
                        user=f"""
Extract the following raw response into a structured format.

Raw response:
{raw_response.output}""",
                    ),
                    logger,
                )  # type: ignore
                logger.info("PostHoc inference call succeeded")
            except Exception as e:
                logger.error(f"PostHoc inference call failed: {e}. Retrying...")
                continue
            finally:
                extract_client_wrapper.model.rate_limit.release(
                    {"tokens": usage.out_tokens}
                )

            logger.debug(f"Received response: {response.escape()}")
            return response, raw_usage

    def format(self) -> str:
        if self.model_selection_policy is None:
            return f"{self.__class__.__name__.replace('Extractor', '')}({{model_name}} -> {{model_name}})"
        return f"{self.__class__.__name__.replace('Extractor', '')}({{model_name}} -> {self.model_selection_policy.char})"


class TokenProbabilityExtractor(Extractor):
    scale: DiscreteScale
    field_name: str

    def inject(self, unit) -> None:
        super().inject(unit)

        if not (hasattr(self.scale, "values") and hasattr(self.scale, "token_support")):
            raise ConfigurationError(
                "TokenProbabilityExtractor requires a Scale with a discrete list of values and a token_support() method"
            )

        model_fields = unit.ResponseSchema.model_fields
        assert len(model_fields) == 1, (
            f"{self.__class__.__name__} only supports a single output field"
        )
        [(self.field_name, field_info)] = model_fields.items()

        self.response_schema = Schema.inline(**{self.field_name: self.scale.T})

    # NOTE: technically this can stream, but it's useless in the single-token case
    def stream(self, stream: bool = False) -> Self:
        if stream:
            raise ConfigurationError(
                "TokenProbabilityExtractor does not support streaming"
            )
        return self

    def extract(
        self,
        client_wrapper: ClientWrapper,
        prompt_message: PromptMessage,
        logger: Logger,
    ) -> Tuple[Schema, Usage]:
        assert self.scale is not None, (
            "TokenProbabilityExtractor.scale must be set before calling extract()"
        )
        logger.debug(
            f"TokenProbabilityExtractor.extract with scale: {self.scale} (token_support: {self.scale.token_support()})"
        )

        messages = prompt_message.to_messages(client_wrapper.model.use_nonce)
        messages[-1]["content"] = config.TOKEN_EXTRACTOR_SPECIFICATION_PROMPT.format(
            content=messages[-1]["content"], scale_prompt=self.scale.prompt()
        )

        # TODO: support multi-tokens
        with client_wrapper.raw_client.defaults(
            temperature=0.0, logprobs=True, max_tokens=6, top_logprobs=20
        ):
            # logit_bias={client_wrapper.encode(token)[0]: 10 for token in self.scale.token_support()},
            response = client_wrapper.raw_client(
                logger=logger, messages=messages, streaming=self.streaming
            )

        logger.debug(
            f"TokenProbabilityExtractor {self.__class__.__name__} received response: {response.choices[0].message.content}"
        )

        usage = Usage(
            in_tokens=response.usage.prompt_tokens,
            out_tokens=response.usage.completion_tokens,
        )

        distribution: Dict[Any, float] = defaultdict(float)
        if hasattr(choice := response.choices[0], "logprobs"):
            logprobs = choice.logprobs
            logger.debug(
                f"TokenProbabilityExtractor {self.__class__.__name__} received logprobs: {logprobs}"
            )
            if isinstance(logprobs, dict):
                logprobs = logprobs["content"][0]["top_logprobs"]
            elif isinstance(logprobs, BaseModel):
                logprobs = logprobs.model_dump()
            else:
                raise ConfigurationError(f"Unsupported logprobs format: {logprobs}")
            if logprobs["content"] is not None:
                probabilities = {
                    lp["token"]: math.exp(lp["logprob"])
                    for lp in logprobs["content"][0]["top_logprobs"]
                    if lp["token"] in self.scale.token_support()
                }
            else:  # TogetherAI
                probabilities = {
                    token: math.exp(lp)
                    for token, lp in zip(logprobs["tokens"], logprobs["token_logprobs"])
                    if token in self.scale.token_support()
                }

            norm = sum(probabilities.values()) if len(probabilities) > 0 else 1
            for token in self.scale.token_support():
                distribution[self.scale.value_mapping_fn(token)] += (
                    probabilities.get(token, 0) / norm
                )
        else:
            raise ConfigurationError(f"""{client_wrapper.model} does not return logprobs.
Switch to a different model provider or to a non-TokenProbabilityExtractor.""")

        logger.debug(
            f"TokenProbabilityExtractor {self.__class__.__name__} received distribution over token support: {distribution}"
        )
        return Schema.inline(distribution=Dict[self.scale.T, float])(
            distribution=distribution
        ), usage  # type: ignore

    def __str__(self) -> str:
        return (
            f"{self.__class__.__name__}(streaming={self.streaming}, scale={self.scale})"
        )


class ArgmaxScoreExtractor(TokenProbabilityExtractor):
    def extract(
        self,
        client_wrapper: ClientWrapper,
        prompt_message: PromptMessage,
        logger: Logger,
    ) -> Tuple[Schema, Usage]:
        response, usage = super().extract(client_wrapper, prompt_message, logger)
        token_probability_distribution = response.distribution  # type: ignore[attr-defined]

        max_token, _ = max(token_probability_distribution.items(), key=lambda x: x[1])
        return self.response_schema(**{self.field_name: max_token}), usage


class SampleScoreExtractor(TokenProbabilityExtractor):
    def extract(
        self,
        client_wrapper: ClientWrapper,
        prompt_message: PromptMessage,
        logger: Logger,
    ) -> Tuple[Schema, Usage]:
        response, usage = super().extract(client_wrapper, prompt_message, logger)
        token_probability_distribution = response.distribution  # type: ignore[attr-defined]

        token, _ = random.choices(
            list(token_probability_distribution.items()),
            weights=list(token_probability_distribution.values()),
        )[0]
        return self.response_schema(**{self.field_name: token}), usage


class WeightedSummedScoreExtractor(TokenProbabilityExtractor):
    def inject(self, unit) -> None:
        super().inject(unit)

        if self.scale.T not in (bool, int, float):
            raise ConfigurationError(
                "WeightedSummedScoreExtractor requires a Scale with boolean, integer, or float values"
            )

        # special case where the output is a float regardless of using a DiscreteScale
        self.response_schema = Schema.inline(**{self.field_name: float})

    def extract(
        self,
        client_wrapper: ClientWrapper,
        prompt_message: PromptMessage,
        logger: Logger,
    ) -> Tuple[Schema, Usage]:
        response, usage = super().extract(client_wrapper, prompt_message, logger)
        token_probability_distribution = response.distribution  # type: ignore[attr-defined]

        weighted = Schema.of(
            output=sum(
                token * probability
                for token, probability in token_probability_distribution.items()
            )
        )
        return self.response_schema(**{self.field_name: weighted.output}), usage  # type: ignore
