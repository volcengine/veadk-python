"""Domain errors returned by scenario evaluation services."""


class ScenarioEvaluationError(RuntimeError):
    """Base class for expected scenario evaluation failures."""


class ScenarioForbidden(ScenarioEvaluationError):
    """The actor does not have permission for the requested operation."""


class ScenarioNotFound(ScenarioEvaluationError):
    """The requested domain object does not exist."""


class ScenarioInvalidTransition(ScenarioEvaluationError):
    """The requested lifecycle transition is not valid."""


class ScenarioUnavailable(ScenarioEvaluationError):
    """Required persistent storage or runtime infrastructure is unavailable."""


class ScenarioEvaluationRunning(ScenarioEvaluationError):
    """Publishing cannot proceed while formal evaluation is active."""
