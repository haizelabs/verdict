from dataclasses import dataclass, field
from typing import List

from verdict import Pipeline
from verdict.common.cot import CoTUnit
from verdict.common.judge import JudgeUnit
from verdict.scale import DiscreteScale
from verdict.schema import Schema

DEFAULT_JUDGE_PROMPT = """
Based on the following, extract the final score.

{previous.thinking}

Score:
"""


DEFAULT_G_EVAL_COHERENCE_PROMPT = """
You will be given one summary written for a news article.

Your task is to rate the summary on one metric.

Please make sure you read and understand these instructions carefully. Please keep this
document open while reviewing, and refer to it as needed.

Evaluation Criteria:

Coherence (1-5) - the collective quality of all sentences. We align this dimension with
the DUC quality question of structure and coherence whereby ”the summary should be
well-structured and well-organized. The summary should not just be a heap of related information, but should build from sentence to sentence to a coherent body of information about a topic.”

Evaluation Steps:

1. Read the news article carefully and identify the main topic and key points.
2. Read the summary and compare it to the news article. Check if the summary covers the main
topic and key points of the news article, and if it presents them in a clear and logical order.
3. Assign a score for coherence on a scale of 1 to 5, where 1 is the lowest and 5 is the highest
based on the Evaluation Criteria.

News Article:
{source.document}

Summary:
{source.summary}

Evaluation Form (scores ONLY):
- Coherence:
"""


@dataclass
class GEvalJudge:
    cot_prompt: str = DEFAULT_G_EVAL_COHERENCE_PROMPT
    cot_model: str = "gpt-4o"
    cot_temperature: float = 0.5
    judge_prompt: str = DEFAULT_JUDGE_PROMPT
    judge_model: str = "gpt-4o-mini"
    judge_temperature: float = 0.0
    retries: int = 3
    kwargs: dict = field(default_factory=dict)
    pipeline: Pipeline = field(init=False)

    def __post_init__(self):
        self.pipeline = (
            Pipeline()
            >> CoTUnit(name="GEval-CoT")
            .prompt(self.cot_prompt)
            .via(
                policy_or_name=self.cot_model,
                retries=self.retries,
                temperature=self.cot_temperature,
                **self.kwargs,
            )
            >> JudgeUnit(name="GEval-Judge", scale=DiscreteScale((1, 5)))
            .prompt(self.judge_prompt)
            .via(
                policy_or_name=self.judge_model,
                retries=self.retries,
                temperature=self.judge_temperature,
                **self.kwargs,
            )
        )

    def run(self, dataset: List[Schema]) -> List[float]:
        results_df, leaf_node_cols = self.pipeline.run_from_list(dataset)
        return list(results_df[leaf_node_cols[0]])


if __name__ == "__main__":
    judge = GEvalJudge()
    test = judge.run(
        [
            Schema.of(
                document="HackerOne: Security researchers I've worked with are blown away by the speed, quality, and variety of prompts Haize Labs generates for their attacks. Its intuitive user interface simplifies the process of designing and executing tests, while the robust reporting and analytics features help turn raw findings into actionable insights. For researchers dedicated to advancing AI reliability, Haize Labs delivers a powerful solution that makes testing smarter and more rewarding.",
                summary="Haize Labs has built out a powerful platform to red-team AI quickly, cheaply, and efficiently. Its platform features an intuitive UI that makes testing, reporting of, and improving AI systems incredibly easy. The Haize product is a must-use for researchers looking to up their eval game.",
            ),
            Schema.of(
                document="HackerOne: Security researchers I've worked with are blown away by the speed, quality, and variety of prompts Haize Labs generates for their attacks. Its intuitive user interface simplifies the process of designing and executing tests, while the robust reporting and analytics features help turn raw findings into actionable insights. For researchers dedicated to advancing AI reliability, Haize Labs delivers a powerful solution that makes testing smarter and more rewarding.",
                summary=" buidling fdas dfsfdasfdkasokfdpsa by haize Labs that is powerful  to team wit hred Intentions, also with quickness, cheapness, efficientness, Intelligence that is Artificial.",
            ),
        ]
    )
    print(test)
