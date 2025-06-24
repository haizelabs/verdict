import inspect
from abc import ABC
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple, Type, Union, get_args

from loguru._logger import Logger
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, create_model
from pydantic.fields import FieldInfo

from verdict.scale import Scale
from verdict.util.exceptions import ConfigurationError
from verdict.util.misc import shorten_string


class Schema(BaseModel, ABC):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    _scales: Dict[str, Scale] = PrivateAttr(default_factory=dict)

    @classmethod
    def get_scale(cls, field_name: str) -> Scale:
        return cls._scales[field_name]

    def __init_subclass__(cls) -> None:
        cls._scales = {}

        for field_name, field_type in cls.__annotations__.items():
            if inspect.isclass(field_type) and issubclass(field_type, Scale):
                if field_name not in cls.__dict__:
                    raise ConfigurationError(f"""No token support specified for Scale field '{field_name}'.

If using a Scale field type, you must specify its token support. For example,

```
class ResponseSchema(Schema):
    score: Scale = DiscreteScale((1, 5))
```
""")

                scale_instance: Scale = cls.__dict__[field_name]
                # Handle (scale, Field(...)) from an Schema.from_values() call
                if isinstance(scale_instance, tuple):
                    scale_instance = scale_instance[0]
                cls.__annotations__[field_name] = scale_instance.T

                cls._scales[field_name] = scale_instance
                setattr(
                    cls,
                    field_name,
                    scale_instance.pydantic_fields(field_name)[field_name][1],
                )

        BaseModel.__init_subclass__()

    @staticmethod
    def infer_pydantic_annotation(obj: Any) -> Any:
        """Infer the appropriate Pydantic annotation for a given object."""

        # Handle None
        if obj is None:
            return None

        # Handle direct types (int, str, etc.)
        if isinstance(obj, type):
            return obj

        obj_type = type(obj)
        if isinstance(obj, Schema):
            return Schema

        # Handle List-like objects
        if isinstance(obj, list) and obj:
            elem_type = Schema.infer_pydantic_annotation(obj[0])
            return List[elem_type]

        # Handle Tuple-like objects
        if isinstance(obj, tuple) and obj:
            elem_types = tuple(Schema.infer_pydantic_annotation(e) for e in obj)
            return Tuple[elem_types]

        # Handle Dict-like objects
        if isinstance(obj, dict) and obj:
            key_type = Schema.infer_pydantic_annotation(next(iter(obj.keys())))
            value_type = Schema.infer_pydantic_annotation(next(iter(obj.values())))
            return Dict[key_type, value_type]

        # Default: Return the object's direct type
        return obj_type

    @staticmethod
    def infer(**kwargs) -> Type["Schema"]:
        # Schema.infer(score=5) -> BaseModel(score=int)
        return type(
            "InferredSchema",
            (Schema,),
            {
                **{
                    field_name: field_value
                    for field_name, field_value in kwargs.items()
                    if isinstance(field_value, Scale)
                },
                "__module__": __name__,
                "__annotations__": {
                    field_name: Schema.infer_pydantic_annotation(field_value)
                    for field_name, field_value in kwargs.items()
                },
            },
        )

    @staticmethod
    def of(**kwargs) -> "Schema":
        # Schema.of(score=5) -> BaseModel(score=int)(score=5)
        return type(
            "InferredSchema",
            (Schema,),
            {
                **kwargs,
                "__module__": __name__,
                "__annotations__": {
                    field_name: Schema.infer_pydantic_annotation(field_value)
                    for field_name, field_value in kwargs.items()
                },
            },
        )(**kwargs)

    @staticmethod
    def inline(**kwargs) -> Type["Schema"]:
        # Schema.inline(score=int) -> BaseModel(score=int)
        return type(
            "InlineSchema",
            (Schema,),
            {
                "__module__": __name__,
                "__annotations__": {
                    field_name: field_type for field_name, field_type in kwargs.items()
                },
            },
        )

    @classmethod
    def empty(cls) -> "Schema":
        return type(
            "EmptySchema",
            (Schema,),
            {
                "__module__": __name__,
            },
        )()

    @classmethod
    def is_empty(cls) -> bool:
        return len(cls.model_fields) == 0

    def __str__(cls_or_self) -> str:
        if isinstance(cls_or_self, type):
            return str(cls_or_self.model_fields)
        return super().__str__()

    def __repr__(self) -> str:
        return self.__str__()

    @classmethod
    def append(cls, **kwargs) -> Type["Schema"]:
        model_fields = {
            **{
                field_name: (field_info.annotation, Field(...))
                for field_name, field_info in cls.model_fields.items()
            },
            **{
                field_name: (t if isinstance(t, tuple) else (t, Field(...)))
                for field_name, t in kwargs.items()
            },
        }

        return create_model(  # type: ignore
            cls.__name__, **model_fields, __base__=Schema
        )

    def add(self, **kwargs) -> "Schema":
        return type(self).append(
            **{
                field_name: Schema.infer_pydantic_annotation(field_value)
                for field_name, field_value in kwargs.items()
            }
        )(**{**self.model_dump(), **kwargs})

    @classmethod
    def prepend(cls, **kwargs) -> Type["Schema"]:
        model_fields = {
            **{
                field_name: (t if isinstance(t, tuple) else (t, Field(...)))
                for field_name, t in kwargs.items()
            },
            **{
                field_name: (field_info.annotation, Field(...))
                for field_name, field_info in cls.model_fields.items()
            },
        }

        return create_model(  # type: ignore
            cls.__name__, **model_fields, __base__=Schema
        )

    @staticmethod
    def from_values(**kwargs) -> "Schema":
        return create_model(  # type: ignore
            "Schema",
            **{
                name: (Schema.infer_pydantic_annotation(value), Field(...))
                for name, value in kwargs.items()
            },
            __base__=Schema,
        )(**kwargs)

    def escape(self) -> str:
        representation = str(self).replace("{", "{{").replace("}", "}}")
        return shorten_string(representation)

    def conform(
        self, expected: Type["Schema"], logger: Optional[Logger] = None
    ) -> "Schema":
        """
        Conform the current schema to the expected schema.
        For a missing field in this Schema (eg, in expected, but not in type(self)),
            1. Check if there is a default factory for the field in expected. If so, use that.
            2. Copy the first field in `self` that matches the type of the expected field.
        """
        current = self

        current_lookup = type(current)._fieldinfo_lookup()
        expected_lookup = expected._fieldinfo_lookup()

        # 1. Set defaults
        for expected_field_name, expected_field_info in expected.model_fields.items():
            key = Schema.generate_key(expected_field_info)

            # names + types match, so we're good
            if (
                expected_field_name in current.model_fields
                and key
                == Schema.generate_key(current.model_fields[expected_field_name])
            ):
                continue

            # default/default factory
            if not expected_field_info.is_required():
                current = current.add(
                    **{
                        expected_field_name: (
                            field_value := expected_field_info.default_factory()
                            if expected_field_info.default_factory is not None
                            else expected_field_info.default
                        )
                    }
                )

                current_lookup = type(current)._fieldinfo_lookup()
                if logger:
                    logger.info(
                        f"Constructed default input field {expected_field_name}={field_value} from {current}"
                    )

        # 2. Copy fields
        for expected_field_name, expected_field_info in expected.model_fields.items():
            key = Schema.generate_key(expected_field_info)

            # names + types match, so we're good
            if (
                expected_field_name in current.model_fields
                and key
                == Schema.generate_key(current.model_fields[expected_field_name])
            ):
                continue

            if len(current_lookup[key]) < len(expected_lookup[key]):
                raise ConfigurationError(
                    f"Cannot cast input. Not enough fields with FieldInfo: {expected_field_info.__str__()} (found {len(current_lookup[key])}, but we need to populate {len(expected_lookup[key])})"
                )

            # find a compatible field in the current schema
            found: bool = False
            for field_name, field_info in current.model_fields.items():
                if key == Schema.generate_key(field_info):
                    current = current.add(
                        **{expected_field_name: getattr(current, field_name)}
                    )
                    current_lookup = type(current)._fieldinfo_lookup()
                    if logger:
                        logger.info(
                            f"Copied field {field_name}={getattr(current, field_name)} to {expected_field_name}"
                        )
                    found = True
                    break

            if found:
                continue

            raise ConfigurationError(
                f"Cannot conform {self} to {expected}. Field compatible with type '{field_info.__str__()}' not found in the input model."
            )

        return current

    @staticmethod
    def generate_key(field_info: FieldInfo) -> str:
        def remove_optional(typ: Type) -> Type:
            if hasattr(typ, "__origin__") and typ.__origin__ is Union:
                args = tuple(arg for arg in get_args(typ) if arg is not type(None))
                if len(args) == 1:
                    return args[0]
                return Union[args]
            return typ

        ATTRIBUTES_FOR_EQUIVALENCE = [
            "le",
            "ge",
            "gt",
            "lt",
            "eq",
            "ne",
            "ge",
            "le",
            "metadata",
        ]  # metadata includes pattern
        keys = [f"{remove_optional(field_info.annotation)}"]
        keys += [
            f"{k}={v}"
            for k, v in zip(
                ATTRIBUTES_FOR_EQUIVALENCE,
                map(
                    lambda attr: getattr(field_info, attr, None),
                    ATTRIBUTES_FOR_EQUIVALENCE,
                ),
            )
        ]
        return str(hash(",".join(keys)))

    @classmethod
    def _fieldinfo_lookup(cls) -> Dict[str, Type]:
        lookup = defaultdict(list)
        for field_name, field_info in cls.model_fields.items():
            lookup[Schema.generate_key(field_info)].append((field_name, field_info))
        return lookup
