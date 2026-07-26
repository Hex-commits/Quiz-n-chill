class AppError(Exception):
    """Base class for errors that map onto a specific HTTP status.

    Services raise these; `main.py` installs a handler that turns them into a
    JSON body. Keeping services free of `HTTPException` means they stay testable
    without a request context.
    """

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
