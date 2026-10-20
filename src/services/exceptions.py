from fastapi import HTTPException, status


class NotFoundException(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class PromoCodeError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, detail)


class InvalidTransitionError(Exception):
    pass


class InternalServerError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            'internal_error',
        )
