from __future__ import annotations


class DrpgApiError(Exception):
    """Base exception for API errors."""


class AuthenticationError(DrpgApiError):
    """Raised when API token is invalid."""


class DownloadError(DrpgApiError):
    """Raised when download preparation fails."""
