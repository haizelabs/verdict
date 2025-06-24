import ast
import inspect
import random
import re
import string
import textwrap
from abc import ABC, abstractmethod
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple, Type, Union

from loguru._logger import Logger
from typing_extensions import Self

from verdict.image import Image
from verdict.schema import Schema
from verdict.util.exceptions import PromptError

SECTION_REGEX = re.compile(r"@(\w+)(.*?)(?=@\w+|$)", re.DOTALL)


class PromptRegistry(type):
    _registry: Dict[str, Type["Prompt"]] = {}

    @staticmethod
    def extract_sections(template: str) -> Tuple[Optional[str], Optional[str], bool]:
        matches = SECTION_REGEX.findall(template)

        sections = {f"@{section}": content for section, content in matches}

        # Assign leading text to '@user' only if it exists and '@user' is not explicitly defined
        leading_text = template.split("@", 1)[0]
        if leading_text and "@user" not in sections:
            sections["@user"] = leading_text

        return sections.get("@system"), sections.get("@user"), "@no_format" in sections

    @staticmethod
    def strip_prompt_template(prompt: str) -> str:
        lines = prompt.splitlines()

        # Remove leading empty lines
        while lines and not lines[0].strip():
            lines.pop(0)

        # Remove trailing empty lines
        while lines and not lines[-1].strip():
            lines.pop()

        # Unindent the remaining lines and reassemble the docstring
        return "\n".join(line.lstrip() for line in lines)

    def __new__(cls, name, bases, dct) -> Type["Prompt"]:
        klass = super().__new__(cls, name, bases, dct)

        # only add named classes to the registry
        if name and not name.startswith("_") and name != "Prompt":
            cls._registry[name] = klass

        if not klass.__doc__:
            raise PromptError(f"Prompt {klass.__name__} must have __doc__.")

        if "" in (klass.extract_keys(klass.__doc__)):
            raise PromptError(f"All keys must be named in Prompt {klass.__name__}.")

        klass.system_prompt_template, klass.user_prompt_template, no_format = (
            klass.extract_sections(klass.__doc__)
        )
        assert klass.user_prompt_template is not None, (
            "User prompt template must be specified."
        )

        if not no_format:
            klass.user_prompt_template = klass.strip_prompt_template(
                klass.user_prompt_template
            )
            if klass.system_prompt_template:
                klass.system_prompt_template = klass.strip_prompt_template(
                    klass.system_prompt_template
                )

        return klass

    def __getattr__(self, name: str) -> Type["Prompt"]:
        if name in self._registry:
            return self._registry[name]
        else:
            raise PromptError(f"Prompt {name} not found in PromptRegistry._registry.")

    @staticmethod
    def compatible_prompts(unit: Type["Promptable"]) -> List[Type["Prompt"]]:
        return [
            prompt
            for prompt in PromptRegistry._registry.values()
            if prompt().supports(unit)
        ]


class PromptMessage(NamedTuple):
    system: Optional[str]
    user: str
    input_schema: Optional[Schema] = None

    def _get_image_values(self, input_schema: Optional[Schema] = None) -> List:
        image_values = []
        if input_schema is None:
            return image_values

        for field_value in input_schema.model_dump().values():
            if "type" in field_value and "image/" in field_value["type"]:
                image_values.append(field_value)

        return image_values

    def to_messages(
        self, add_nonce: bool = False
    ) -> List[Dict[str, str | List[Dict[str, str | Dict[str, str]]]]]:
        nonce = (
            "".join(random.choices(string.ascii_letters, k=10)) + "\n"
            if add_nonce
            else ""
        )
        content = [{"type": "text", "text": nonce + self.user}]

        image_values = self._get_image_values(self.input_schema)
        if image_values:
            for image in image_values:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image['type']};base64,{image['data']}"
                        },
                    }
                )

        messages = [{"role": "user", "content": content}]
        if self.system:
            messages.insert(0, {"role": "system", "content": nonce + self.system})
        return messages


RESERVED_KEYS = set(["input", "unit", "previous", "source", "prompt"])


class Prompt(metaclass=PromptRegistry):
    """
    A prompt template that can be used to generate a prompt for an LLM.
    Supports formatting with the keys of a Schema / pydantic.BaseModel.

    {key} will be replaced with the value of the key in the input at runtime.
    Indentation is preserved in the output.
    """

    system_prompt_template: Optional[str]
    user_prompt_template: str

    caller_locals: Dict[str, Any] = {}

    @staticmethod
    def from_template(template: str) -> "Prompt":
        return type("", (Prompt,), {"__doc__": template})()

    @staticmethod
    def extract_keys(template: str, exclude_reserved: bool = True) -> Set[str]:
        def extract_variables(template: str) -> Set[str]:
            variables = set()

            placeholder_pattern = r"(?<!\{)\{([^{}]+?)\}(?!\})"
            placeholders = re.findall(placeholder_pattern, template)

            for placeholder in placeholders:
                try:
                    tree = ast.parse(placeholder, mode="eval")

                    class VariableVisitor(ast.NodeVisitor):
                        def visit_Name(self, node) -> None:
                            variables.add(node.id)

                        def visit_Attribute(self, node) -> None:
                            while isinstance(node, ast.Attribute):
                                node = node.value
                            if isinstance(node, ast.Name):
                                variables.add(node.id)

                    VariableVisitor().visit(tree)
                except SyntaxError:
                    variables.add(placeholder.split(".")[0])

            return variables

        if not exclude_reserved:
            return extract_variables(template)
        return extract_variables(template) - RESERVED_KEYS

    def get_all_keys(self) -> Set[str]:
        keys = set()

        if self.system_prompt_template:
            keys |= Prompt.extract_keys(
                self.system_prompt_template, exclude_reserved=False
            )

        keys |= Prompt.extract_keys(self.user_prompt_template, exclude_reserved=False)

        return keys

    @property
    def keys(self) -> Set[str]:
        return self.get_all_keys() - RESERVED_KEYS - set(self.caller_locals.keys())

    def format(
        self,
        input_schema: Schema,
        unit: "Promptable",
        previous: Any,
        source: Schema,
        logger: Optional[Logger] = None,
    ) -> PromptMessage:
        for illegal_symbol in ["{{", "}}"]:
            for prompt in [self.system_prompt_template, self.user_prompt_template]:
                if prompt is not None and illegal_symbol in prompt:
                    if logger:
                        logger.warning(
                            f"Prompt contains '{illegal_symbol}'. Variable likely not getting evaluated."
                        )

        format_kwargs = (
            {"input": input_schema}
            | {"unit": unit}
            | {"previous": previous}
            | {"source": source}
        )

        for key, value in self.caller_locals.items():
            if key not in format_kwargs and not key.startswith("__"):
                format_kwargs[key] = value

        return PromptMessage(
            system=(
                self.auto_format(self.system_prompt_template, format_kwargs)
                if self.system_prompt_template
                else None
            ),
            user=self.auto_format(self.user_prompt_template, format_kwargs),
            input_schema=input_schema,
        )

    @staticmethod
    def auto_format(template: str, context: Dict[str, Any]) -> str:
        single_placeholder_pattern = r"(?<!\{)\{([^{}]+?)\}(?!\})"
        matches = re.findall(single_placeholder_pattern, template)

        for match in matches:
            try:
                value = eval(match, {}, context)
                template = template.replace(f"{{{match}}}", str(value))
            except Exception as e:
                raise PromptError(
                    textwrap.dedent(
                        f"""
                        Failed to evaluate Prompt placeholder '{match}' in the following context.

                        Context: {context}
                        """
                    )
                ) from e

        return template


class Promptable(ABC):
    _prompt: Prompt

    def prompt(self, prompt: Union[str, Prompt]) -> Self:
        if isinstance(prompt, str):
            self._prompt = Prompt.from_template(prompt)
        else:
            self._prompt = prompt

        frame = inspect.currentframe().f_back
        self._prompt.caller_locals = frame.f_locals

        return self

    @abstractmethod
    def populate_prompt_message(self, input: Schema, logger: Logger) -> PromptMessage:
        pass
