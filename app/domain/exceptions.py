"""Domain semantic exceptions."""


class DomainError(Exception):
    """Base domain exception."""


class InvalidConstraints(DomainError):
    """Raised when trip constraints are semantically invalid."""

