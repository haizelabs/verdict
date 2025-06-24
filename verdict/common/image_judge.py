import base64

import requests

from verdict import Pipeline
from verdict.core.primitive import Unit
from verdict.image import Image
from verdict.scale import DiscreteScale
from verdict.schema import Field, Schema


def download_image(url: str) -> str:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return base64.b64encode(response.content).decode("utf-8")


def get_test_image(url: str) -> str:
    return download_image(url)


class ImageJudgeUnit(Unit):
    _char: str = "ImageJudge"

    class ResponseSchema(Schema):
        score: int = Field(..., ge=1, le=5, description="Score from 1-5")
        explanation: str = Field(..., description="Explanation for the score")


class ImagePairwiseJudgeUnit(Unit):
    _char: str = "ImagePairwiseJudge"

    class ResponseSchema(Schema):
        choice: DiscreteScale = DiscreteScale(["A", "B"])
        explanation: str = Field(..., description="Explanation for the score")


def test_single_image():
    judge = ImageJudgeUnit().prompt("""
    Rate the quality of this image on a scale of 1-5, where:
    1 = Very poor quality (blurry, low resolution, hard to see details)
    5 = Excellent quality (sharp, clear, high resolution, easy to see details)
    
    Image: {input.image}
    Question: {input.question}
    
    Provide your rating and explanation:
    """)

    test_data = [
        Schema.of(
            image=Image(
                type="image/png",
                data=get_test_image("https://httpbin.org/image/png"),
            ),
            question="How would you rate the overall quality of this image?",
        ),
        Schema.of(
            image=Image(
                type="image/jpeg",
                data=get_test_image("https://httpbin.org/image/jpeg"),
            ),
            question="Rate the clarity and sharpness of this image",
        ),
    ]

    pipeline = Pipeline() >> judge
    results_df, leaf_node_cols = pipeline.run_from_list(test_data)

    print("--- Results ---")
    print("Score:", results_df[leaf_node_cols[0]][0])
    print("Explanation:", results_df[leaf_node_cols[1]][0])


def test_pairwise_image():
    judge = (
        ImagePairwiseJudgeUnit()
        .prompt("""
    Which image is more like a deer? 
    If you think the first image is more like a deer, choose A. If you think the second image is more like a deer, choose B.
    
    {input.image_a}
    {input.image_b}
    
    Provide your choice and explanation:
    """)
        .via("gpt-4o")
    )

    test_data = [
        Schema.of(
            image_a=Image(
                type="image/png",
                data=get_test_image("https://httpbin.org/image/png"),
            ),
            image_b=Image(
                type="image/jpeg",
                data=get_test_image("https://httpbin.org/image/jpeg"),
            ),
        ),
    ]

    pipeline = Pipeline() >> judge
    results_df, leaf_node_cols = pipeline.run_from_list(test_data)

    print("--- Results ---")
    print("Choice:", results_df[leaf_node_cols[0]][0])
    print("Explanation:", results_df[leaf_node_cols[1]][0])


if __name__ == "__main__":
    # test_single_image()
    test_pairwise_image()
