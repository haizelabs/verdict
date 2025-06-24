import string
from typing import List, Optional

from verdict.core.primitive import Unit
from verdict.scale import DiscreteScale, LikertScale, Scale
from verdict.schema import Field, Schema


class JudgeUnit(Unit):
    """
    Direct score judge.
    """

    _char: str = "DirectScoreJudge"

    class ResponseSchema(Schema):
        score: Scale = LikertScale()

    def __init__(
        self, scale: Optional[Scale] = None, explanation: bool = False, **kwargs
    ):
        if scale is not None:
            self.OutputSchema = self.ResponseSchema = Schema.infer(score=scale)  # type: ignore

        self.scale = self.ResponseSchema.get_scale("score")

        if explanation:
            self.OutputSchema = self.ResponseSchema = self.ResponseSchema.prepend(
                explanation=str
            )  # type: ignore

        super().__init__(**kwargs)


class BestOfKJudgeUnit(Unit):
    _char: str = "BestOfKJudge"

    class InputSchema(Schema):
        # need a sentinel for empty, but using [''] for now makes type inference simple
        options: List[str] = Field(default=[""])

    class ResponseSchema(Schema):
        choice: DiscreteScale = DiscreteScale(["A", "B"])

    class OutputSchema(Schema):
        chosen: str

    def __init__(
        self,
        k: int = 2,
        response_options: Optional[DiscreteScale] = None,
        explanation: bool = False,
        original: bool = False,
        **kwargs,
    ):
        self.k = k
        self.explanation = explanation
        self.original = original

        response_options = response_options or DiscreteScale(
            list(string.ascii_uppercase[:k])
        )
        self.ResponseSchema = Schema.infer(choice=response_options)  # type: ignore

        self.scale = self.ResponseSchema.get_scale("choice")

        if explanation:
            self.ResponseSchema = self.ResponseSchema.prepend(explanation=str)  # type: ignore
            self.OutputSchema = self.OutputSchema.prepend(explanation=str)  # type: ignore

        super().__init__(**kwargs)

    def validate(self, input: InputSchema, response: ResponseSchema) -> bool:
        if self.original:
            assert len(input.options) != [""], (
                "Pass the options in InputSchema.options to index original choices."
            )
            assert len(input.options) == self.k, (
                f"Number of input options must equal {self.k}"
            )

    def process(self, input: InputSchema, response: ResponseSchema) -> OutputSchema:
        if not self.original:
            return response

        fields = {
            "chosen": input.options[
                self.scale.values.index(self.scale.value_mapping_fn(response.choice))
            ]
        }
        if self.explanation:
            fields["explanation"] = response.explanation

        return self.OutputSchema(**fields)


class PairwiseJudgeUnit(BestOfKJudgeUnit):
    """
    Judge unit for pairwise comparison (e.g., 'Response A' vs 'Response B').
    Options should be LLM responses.
    """

    _char: str = "PairwiseJudge"

    def __init__(
        self,
        response_options: Optional[DiscreteScale] = None,
        explanation: bool = False,
        original: bool = False,
        **kwargs,
    ):
        super().__init__(
            k=2,
            response_options=response_options,
            explanation=explanation,
            original=original,
            **kwargs,
        )


class CategoricalJudgeUnit(BestOfKJudgeUnit):
    """
    Judge unit for categorical decisions (e.g., 'Yes' or 'No', 'Harmful' or 'Not Harmful', 'Hallucination' or 'No Hallucination').
    Options should represent discrete categorical choices.
    """

    _char: str = "CategoricalJudge"

    def __init__(
        self,
        categories: Optional[DiscreteScale] = None,
        explanation: bool = False,
        original: bool = False,
        **kwargs,
    ):
        super().__init__(
            k=2,
            response_options=categories,
            explanation=explanation,
            original=original,
            **kwargs,
        )
