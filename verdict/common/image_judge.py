import base64
import textwrap
from dataclasses import dataclass, field
from typing import List, Tuple

from verdict import Image, Pipeline, Unit
from verdict.scale import DiscreteScale
from verdict.schema import Field, Schema


class ImagePairwiseJudgeUnit(Unit):
    _char: str = "ImagePairwiseJudge"

    class ResponseSchema(Schema):
        choice: DiscreteScale = DiscreteScale(["A", "B"])


class ImagePairwiseJudgeUnitWithRationale(ImagePairwiseJudgeUnit):
    class ResponseSchema(ImagePairwiseJudgeUnit.ResponseSchema):
        explanation: str = Field(..., description="Explanation for the choice")


@dataclass
class ImagePairwiseJudge:
    DEFAULT_JUDGE_PROMPT = textwrap.dedent(
        """
        @system
        You are an art critic with exceptional taste in the matters of animated art. You are given two images and you need to judge which one is better.

        @user
        Given the following two images, decide which one is more aesthetically pleasing.

        {source.image_a}
        {source.image_b}

        Your response should be a single letter, either "A" for the first image or "B" for the second image, indicating your choice.
        """
    )

    DEFAULT_JUDGE_PROMPT_WITH_RATIONALE = textwrap.dedent(
        f"""
        {DEFAULT_JUDGE_PROMPT}
        Please provide a rationale for your choice.
        """
    )

    output_categories: DiscreteScale = field(
        default_factory=lambda: DiscreteScale(["A", "B"])
    )
    model: str = "gpt-4.1-mini"
    retries: int = 3
    explanation: bool = False

    def __post_init__(self):
        if self.explanation:
            unit = ImagePairwiseJudgeUnitWithRationale().prompt(
                self.DEFAULT_JUDGE_PROMPT_WITH_RATIONALE
            )
        else:
            unit = ImagePairwiseJudgeUnit().prompt(self.DEFAULT_JUDGE_PROMPT)

        self.pipeline = Pipeline() >> unit.via(
            policy_or_name=self.model, retries=self.retries
        )

    def run(self, dataset: List[Schema]) -> List[str] | Tuple[List[str], List[str]]:
        results_df, leaf_node_cols = self.pipeline.run_from_list(dataset)
        if self.explanation:
            return list(results_df[leaf_node_cols[0]]), list(
                results_df[leaf_node_cols[1]]
            )
        return list(results_df[leaf_node_cols[0]])


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


if __name__ == "__main__":
    judge = ImagePairwiseJudge(explanation=True)

    data = [
        Schema.of(
            image_a=Image("images/nyc-bird.jpeg"),
            image_b=Image("images/sf-bird.jpeg"),
        )
    ]
    results = judge.run(data)
    print(results)
