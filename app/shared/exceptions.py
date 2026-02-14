"""Shared (non-domain) exceptions."""


class ToolError(Exception):
    """Tool invocation failed."""

    def __init__(self, tool: str, message: str):
        self.tool = tool
        super().__init__(f"[{tool}] {message}")


class ExternalServiceError(Exception):
    """External service call failed."""


class KeyMissingError(Exception):
    """Required key is missing."""

    def __init__(self, name: str):
        self.key_name = name
        super().__init__(f"Missing required API key: {name} (configure it in .env)")
