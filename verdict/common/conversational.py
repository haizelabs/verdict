import copy
from dataclasses import dataclass
from itertools import cycle
from typing import List, Optional

from verdict.core.primitive import Unit
from verdict.schema import Field, Schema


@dataclass
class Message:
    role_name: str
    message: str

    def __init__(self, role_name: str, message: str) -> None:
        self.role_name = role_name
        self.message = message

    def __str__(self) -> str:
        return f"<{self.role_name}>\n{self.message}\n</{self.role_name}>"

    def __repr__(self) -> str:
        return str(self)


class Conversation:
    history: List[Message]

    def __init__(self, history: Optional[List[Message]] = None) -> None:
        self.history = history or [Message("<START>", "")]

    def get_roles(self) -> List[str]:
        all_roles = list(map(lambda m: m.role_name, self.history[1:]))

        roles = []
        seen = set()
        for role in all_roles:
            if role not in seen:
                roles.append(role)
                seen.add(role)
        return roles

    def with_roles(self, roles: List[str]) -> "Conversation":
        assert len(roles) == len(self.get_roles()), (
            "Number of roles must match existing role structure"
        )
        for message, role in zip(self.history[1:], cycle(roles)):
            message.role_name = role

        return self

    def with_context(self) -> "Conversation":
        other = self.copy()
        other._with_context = True
        return other

    def __str__(self) -> str:
        starting_index = 0 if getattr(self, "_with_context", False) else 1
        return "\n\n".join(map(str, self.history[starting_index:]))

    def __repr__(self) -> str:
        return str(self)

    def copy(self) -> "Conversation":
        return copy.deepcopy(self)


class ConversationalUnit(Unit):
    @property
    def _char(self) -> str:
        return self.role_name

    class InputSchema(Schema):
        conversation: Conversation = Field(default_factory=Conversation)

    class ResponseSchema(Schema):
        response: str

    class OutputSchema(Schema):
        conversation: Conversation
        response: str

    def __init__(self, role_name: str, number: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self.role_name = role_name
        self.number = number

    def idx(self, value: Optional[int] = None) -> int:
        if value is not None and self.number and "#" not in self.role_name:
            self.role_name = f"{self.role_name} #{value}"
        return super().idx(value)

    def process(self, input: InputSchema, response: ResponseSchema) -> OutputSchema:
        conversation = copy.deepcopy(input.conversation)
        conversation.history.append(
            Message(role_name=self.role_name, message=response.response)
        )
        return self.OutputSchema(conversation=conversation, response=response.response)
