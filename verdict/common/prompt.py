from verdict.prompt import Prompt


class GEvalEvaluationStepsCoTPrompt(Prompt):
    """
    {root.task}

    Evaluation Criteria:
    {criteria.name} ({criteria.scale}) - {criteria.description}

    Evaluation Steps:
    """
