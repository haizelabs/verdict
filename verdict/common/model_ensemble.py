from dataclasses import dataclass, field
from typing import List

from verdict import Layer, Pipeline
from verdict.common.judge import JudgeUnit
from verdict.scale import ContinuousScale
from verdict.schema import Schema
from verdict.transform import MeanPoolUnit
from verdict.util import ratelimit

ratelimit.disable()


@dataclass
class ModelEnsembleJudge:
    judge_prompt: str
    models: List[str]
    pipeline: Pipeline = field(init=False)
    kwargs: dict = field(default_factory=dict)

    def __post_init__(self):
        self.pipeline = (
            Pipeline()
            >> Layer(
                [
                    JudgeUnit(scale=ContinuousScale(1, 5))
                    .prompt(self.judge_prompt)
                    .via(policy_or_name=model, **self.kwargs)
                    for model in self.models
                ]
            )
            >> MeanPoolUnit()
        )

    def run(self, dataset: List[Schema]) -> List[float]:
        results_df, leaf_node_cols = self.pipeline.run_from_list(dataset)
        return list(results_df[leaf_node_cols[0]])


if __name__ == "__main__":
    prompt = """
    Rate this joke's comedic merit: {source.joke}
    """
    judge = ModelEnsembleJudge(
        judge_prompt=prompt,
        models=["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo", "claude-3-5-sonnet-20241022"],
    )
    test = judge.run(
        [
            # Not funny
            Schema.of(
                joke="Why did the chicken cross the road? To get to the other side."
            ),
            # Slightly funnier
            Schema.of(
                joke="Why didn't the chicken cross the road? Because there was a KFC on the other side."
            ),
        ]
    )
    print(test)
