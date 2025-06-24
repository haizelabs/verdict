import pytest

from verdict.schema import Field, Schema
from verdict.util.exceptions import VerdictDeclarationTimeError


def test_schema_conform():
    class SchemaA(Schema):
        a: str
        x: int

    class SchemaB(Schema):
        y: int
        name_factory: str = Field(default_factory=lambda: "verdict")
        name_default: str = Field(default="verdict")
        b: str

    input_instance = SchemaA(a="test", x=42)

    transformed_instance = input_instance.conform(SchemaB)
    assert set(transformed_instance.model_fields.keys()) == set(
        ["a", "x", "y", "name_factory", "name_default", "b"]
    )


def test_schema_conform_fail():
    class SchemaA(Schema):
        a: int
        b: int

    class SchemaB(Schema):
        x: int
        y: int
        z: int

    input_instance = SchemaA(a=42, b=42)
    with pytest.raises(VerdictDeclarationTimeError):
        input_instance.conform(SchemaB)
