"""Exceptions shared by the Muv services (Qt-free so they are easy to test)."""


class ServiceError(Exception):
    """An expected failure whose message is safe to show on screen and in logs."""


class ConfigurationError(ServiceError):
    """The service cannot work until the user fixes the configuration.

    Retrying quickly will not help, so the polling loop waits a full interval.
    """


class TransitError(ServiceError):
    """A bus ETA request failed or returned something unusable."""


def describe_request_error(exc: Exception) -> str:
    """Return a short description of a ``requests`` exception without secrets.

    ``str(exc)`` usually contains the full request URL, which for OpenWeatherMap
    includes the API key (``?appid=...``). Never log or display that text.
    """
    import requests

    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, requests.Timeout):
        return "request timed out"
    if isinstance(exc, requests.ConnectionError):
        return "network unreachable"
    return type(exc).__name__
