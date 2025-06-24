# high-level
class VerdictSystemError(Exception):
    """
    Non user-defined errors that are related to the core Verdict framework.
    """


class VerdictDeclarationTimeError(Exception):
    """
    Raised for a deterministic (i.e., cannot be fixed with a retry) error that
    occurs as a result of a configuration error.

    Examples:
    * using an incompatible Extractor with a particular Scale
    * invalid keys in a Prompt
    """


class VerdictExecutionTimeError(Exception):
    """
    Raised for a non-deterministic (i.e., can be fixed with a retry) error that
    occurs at execution time.

    Examples:
    * provider error
        * rate-limit
        * function calling validation
        * timeout
    """


# Declaration-time errors
class InputSchemaMismatchError(VerdictDeclarationTimeError):
    pass


class PromptError(VerdictDeclarationTimeError):
    pass


class ConfigurationError(VerdictDeclarationTimeError):
    """
    User error with the configuration of a Verdict pipeline.
    """


class PostProcessError(VerdictDeclarationTimeError):
    """
    Indicates an error in the process() method of a Unit.
    """

    pass


class PropagateError(VerdictDeclarationTimeError):
    """
    Indicates an error in the passed propagator function.
    """

    pass


# Execution-time errors
class StructuredOutputError(VerdictExecutionTimeError):
    pass


class ProviderError(VerdictExecutionTimeError):
    pass


class PostValidationError(VerdictExecutionTimeError):
    pass
