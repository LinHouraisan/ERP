from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 409, details=None):
        self.code, self.message, self.status, self.details = code, message, status, details


def install_errors(app: FastAPI):
    @app.middleware('http')
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers['X-Request-ID'] = request.state.request_id
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        return JSONResponse(status_code=error.status, content={
            'code': error.code, 'message': error.message,
            'request_id': request.state.request_id, 'details': error.details,
        })

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, error: RequestValidationError):
        return await domain_error(request, DomainError('INVALID_INPUT', '输入不合法，请检查字段', 422,
            [{'field': '.'.join(map(str, e['loc'])), 'type': e['type']} for e in error.errors()]))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        return await domain_error(request, DomainError('HTTP_ERROR', '请求的接口不存在' if error.status_code == 404 else '请求无法处理', error.status_code))

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        return await domain_error(request, DomainError('INTERNAL_ERROR', '服务暂不可用；若已提交办理，请刷新受理记录并核对结果', 500))
