"""Normalized provider failures safe to translate at the API boundary."""


class ProviderExecutionError(Exception):
    """A provider rejected or failed a request."""


class ProviderTimeoutError(ProviderExecutionError):
    """A provider exceeded its bounded execution time."""


class ProviderQuotaError(ProviderExecutionError):
    """Provider free-tier quota or rate limit rejected a call."""


class ProviderCredentialError(ProviderExecutionError):
    """Provider rejected the configured credentials."""


class ProviderModelError(ProviderExecutionError):
    """Provider no longer serves the requested model."""
