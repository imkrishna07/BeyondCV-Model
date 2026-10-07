"""Sanitized platform collection errors shared by coding profile analyzers."""


class CodingPlatformError(Exception):
    def __init__(self, platform: str, message: str):
        super().__init__(message)
        self.platform = platform


class InvalidCodingUsername(CodingPlatformError):
    pass


class CodingProfileNotFound(CodingPlatformError):
    pass


class CodingRateLimitError(CodingPlatformError):
    pass


class CodingAPIError(CodingPlatformError):
    pass


class CodingNetworkError(CodingPlatformError):
    pass
