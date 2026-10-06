"""Normalized provider failures safe to translate at the API boundary."""


class ProviderExecutionError(Exception):
    """A provider rejected or failed a request."""


class ProviderTimeoutError(ProviderExecutionError):
    """A provider exceeded its bounded execution time."""
