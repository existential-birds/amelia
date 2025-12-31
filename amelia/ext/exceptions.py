"""Extension-related exceptions."""


class PolicyDeniedError(Exception):
    """Raised when a policy hook denies an operation.

    Attributes:
        reason: Human-readable reason for the denial.
        hook_name: Name of the policy hook that denied the operation (if known).
    """

    def __init__(self, reason: str, hook_name: str | None = None) -> None:
        """Initialize PolicyDeniedError.

        Args:
            reason: Human-readable reason for the denial.
            hook_name: Name of the policy hook that denied the operation (optional).
        """
        self.reason = reason
        self.hook_name = hook_name

        if hook_name:
            message = f"Policy denied by {hook_name}: {reason}"
        else:
            message = f"Policy denied: {reason}"

        super().__init__(message)
