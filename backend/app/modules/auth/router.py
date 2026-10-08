from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete

from app.core.config import Settings
from app.core.db import get_db
from app.core.security import current_user, require_origin
from app.modules.auth.models import AuthSession
from app.modules.auth.schemas import CurrentUser, Login
from app.modules.auth.service import csrf, digest, login

router = APIRouter(prefix='/api/v1/auth', tags=['身份'])


@router.post('/login', response_model=CurrentUser)
async def sign_in(data: Login, request: Request, response: Response, db=Depends(get_db)):
    require_origin(request)
    user, token = await login(db, data.username, data.password)
    response.set_cookie('erp_session', token, httponly=True, secure=Settings().cookie_secure, samesite='strict', max_age=8*3600, path='/api')
    return CurrentUser(user_id=user.id, store_id=user.store_id, username=user.username, role=user.role, csrf_token=csrf(token))


@router.get('/me', response_model=CurrentUser)
async def me(user=Depends(current_user)):
    return user


@router.post('/logout')
async def logout(request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)):
    await db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(request.cookies.get('erp_session', ''))))
    await db.commit()
    response.delete_cookie('erp_session', path='/api')
    return {'logged_out': True}
