"""Domain exception hierarchy for SparkPilot.

All service-layer errors should inherit from SparkPilotError so API and
worker layers can map them consistently.

Hierarchy:
    SparkPilotError
    |- EntityNotFoundError
    |- ConflictError
    |- GoneError
    |- ValidationError
    |- QuotaExceededError
    |- ProvisioningError
    |  `- ProvisioningPermanentError
    `- (extend here as needed)
"""

from __future__ import annotations


class SparkPilotError(Exception):
    """Base for all domain errors raised by the service layer."""

    def __init__(self, detail: str, *, status_code: int = 500) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class EntityNotFoundError(SparkPilotError):
    """Requested entity does not exist."""

    def __init__(self, detail: str = "Entity not found.") -> None:
        super().__init__(detail, status_code=404)


class ConflictError(SparkPilotError):
    """Operation conflicts with existing state."""

    def __init__(self, detail: str = "Conflict.") -> None:
        super().__init__(detail, status_code=409)


class GoneError(SparkPilotError):
    """Requested resource existed but is no longer usable."""

    def __init__(self, detail: str = "Gone.") -> None:
        super().__init__(detail, status_code=410)


class ValidationError(SparkPilotError):
    """Request payload or state failed validation."""

    def __init__(self, detail: str = "Validation error.") -> None:
        super().__init__(detail, status_code=422)


class QuotaExceededError(SparkPilotError):
    """Resource quota or rate limit exceeded."""

    def __init__(self, detail: str = "Quota exceeded.") -> None:
        super().__init__(detail, status_code=429)


class ProvisioningError(SparkPilotError):
    """Error during environment provisioning."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, status_code=500)


class ProvisioningPermanentError(ProvisioningError):
    """Permanent provisioning failure (no retry will help)."""
