import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("ledger")


def error_response(status_code: int, code: str, message: str, details=None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"

    def __init__(self, message: str, details=None):
        super().__init__(message)
        self.message = message
        self.details = details


class AccountNotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "ACCOUNT_NOT_FOUND"

    def __init__(self, account_id):
        super().__init__(f"Account {account_id} not found", {"account_id": str(account_id)})


class InsufficientBalance(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INSUFFICIENT_BALANCE"

    def __init__(self, account_id, balance, amount):
        super().__init__(
            "Insufficient balance for this debit",
            {"account_id": str(account_id), "balance": str(balance), "requested_amount": str(amount)},
        )


class DuplicateTransaction(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "DUPLICATE_TRANSACTION"

    def __init__(self, existing_transaction: dict):
        super().__init__(
            "A transaction with this reference_id already exists for this account",
            {"existing_transaction": existing_transaction},
        )


def _clean_validation_errors(errors) -> list[dict]:
    out = []
    for err in errors:
        loc = [str(p) for p in err.get("loc", ())]
        out.append({"field": ".".join(loc), "message": err.get("msg", "Invalid value")})
    return out


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError):
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError):
        errors = exc.errors()
        details = _clean_validation_errors(errors)

        if any(tuple(e.get("loc", ()))[:1] == ("query",) and tuple(e["loc"])[1:2] in (("page",), ("limit",))
               for e in errors):
            return error_response(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_PAGINATION",
                "page must be an integer >= 1 and limit an integer between 1 and the maximum page size",
                details,
            )

        if any(e.get("type") == "json_invalid" for e in errors):
            return error_response(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "INVALID_REQUEST_BODY", "Request body is not valid JSON", details
            )

        first = details[0] if details else {"field": "", "message": "Invalid request"}
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "VALIDATION_ERROR",
            f"{first['field']}: {first['message']}" if first["field"] else first["message"],
            details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException):
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        return error_response(exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception):
        logger.exception("Unhandled error", exc_info=exc)
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "Something went wrong")
