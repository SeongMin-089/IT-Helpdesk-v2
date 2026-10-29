import re
from contextvars import ContextVar

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import config
from app.schemas import AuthLogin
from app.services import odoo
from app.transformers import oca_relation


router = APIRouter(prefix="/api/auth")

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{42,128}$")
GROUPS = {
    "employee": "base.group_user",
    "helpdesk_personal": "helpdesk_mgmt.group_helpdesk_user_own",
    "helpdesk_team": "helpdesk_mgmt.group_helpdesk_user_team",
    "helpdesk_user": "helpdesk_mgmt.group_helpdesk_user",
    "helpdesk_manager": "helpdesk_mgmt.group_helpdesk_manager",
}
CURRENT_USER = ContextVar("it_helpdesk_current_user", default=None)


def require_trusted_origin(request):
    origin = (request.headers.get("origin") or "").rstrip("/")
    if not origin or origin not in config.AUTH_ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="허용되지 않은 요청 출처입니다.")


def set_session_cookie(response, session_id):
    response.set_cookie(
        key=config.AUTH_COOKIE_NAME,
        value=session_id,
        max_age=config.AUTH_SESSION_MAX_AGE,
        path="/api",
        httponly=True,
        secure=config.AUTH_COOKIE_SECURE,
        samesite=config.AUTH_COOKIE_SAMESITE,
    )


def clear_session_cookie(response):
    response.delete_cookie(
        key=config.AUTH_COOKIE_NAME,
        path="/api",
        secure=config.AUTH_COOKIE_SECURE,
        httponly=True,
        samesite=config.AUTH_COOKIE_SAMESITE,
    )


def auth_error_response(error):
    response = JSONResponse(
        status_code=error.status_code,
        content={"detail": error.detail},
    )
    if error.status_code in (401, 403):
        clear_session_cookie(response)
    return response


def get_cookie_session(request):
    session_id = request.cookies.get(config.AUTH_COOKIE_NAME)
    if not session_id or not SESSION_ID_PATTERN.fullmatch(session_id):
        raise HTTPException(status_code=401, detail="유효한 로그인 세션이 없습니다.")
    return session_id


def get_verified_user(session_id):
    session_info = odoo.get_session_info(session_id)
    user_id = session_info.get("uid")
    records = odoo.session_call_kw(
        session_id,
        "res.users",
        "read",
        args=[[user_id], ["id", "name", "partner_id", "active"]],
    )
    if (
        not isinstance(records, list)
        or len(records) != 1
        or records[0].get("id") != user_id
        or not records[0].get("active")
    ):
        raise HTTPException(status_code=401, detail="Odoo 사용자를 확인할 수 없습니다.")

    groups = {
        name: bool(
            odoo.session_call_kw(
                session_id,
                "res.users",
                "has_group",
                args=[[user_id], xml_id],
            )
        )
        for name, xml_id in GROUPS.items()
    }
    is_agent = groups["helpdesk_user"] or groups["helpdesk_manager"]
    if not is_agent and not groups["employee"]:
        raise HTTPException(status_code=403, detail="내부 직원 계정만 이용할 수 있습니다.")

    user = records[0]
    partner = oca_relation(user.get("partner_id"))
    if partner is None:
        raise HTTPException(status_code=403, detail="연결된 Odoo 연락처가 없습니다.")
    return {
        "id": user["id"],
        "name": user.get("name") or "",
        "partner_id": partner["id"] if partner else None,
        "partner": partner,
        "role": "agent" if is_agent else "employee",
        "groups": groups,
    }


async def require_authenticated_user(request: Request):
    session_id = get_cookie_session(request)
    user = await run_in_threadpool(get_verified_user, session_id)
    request.state.auth_user = user
    token = CURRENT_USER.set(user)
    try:
        yield user
    finally:
        CURRENT_USER.reset(token)


def get_current_user():
    user = CURRENT_USER.get()
    if user is None:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    return user


def require_agent():
    user = get_current_user()
    if user["role"] != "agent":
        raise HTTPException(status_code=403, detail="IT 담당자 권한이 필요합니다.")
    return user


def ensure_ticket_owner(ticket, conceal=True):
    user = get_current_user()
    if user["role"] == "agent":
        return user
    if not is_ticket_owner(ticket, user):
        raise HTTPException(
            status_code=404 if conceal else 403,
            detail="문의를 찾을 수 없습니다." if conceal else "문의 접근 권한이 없습니다.",
        )
    return user


def is_ticket_owner(ticket, user=None):
    user = user or get_current_user()
    partner_id = ticket.get("partner_id")
    ticket_partner_id = partner_id[0] if isinstance(partner_id, (list, tuple)) else partner_id
    return ticket_partner_id == user["partner_id"]


def require_ticket_owner(ticket, conceal=True):
    if not is_ticket_owner(ticket):
        raise HTTPException(
            status_code=404 if conceal else 403,
            detail="문의를 찾을 수 없습니다." if conceal else "문의 접근 권한이 없습니다.",
        )
    return get_current_user()


@router.post("/login")
def login(data: AuthLogin, request: Request, response: Response):
    require_trusted_origin(request)
    previous_session_id = request.cookies.get(config.AUTH_COOKIE_NAME)
    session_id = None
    try:
        session_id, _session_info = odoo.authenticate_session(
            data.login,
            data.password.get_secret_value(),
        )
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise HTTPException(status_code=502, detail="Odoo 세션 형식이 올바르지 않습니다.")
        if previous_session_id and previous_session_id == session_id:
            raise HTTPException(status_code=401, detail="새 로그인 세션을 만들지 못했습니다.")
        user = get_verified_user(session_id)
    except HTTPException as error:
        if session_id and SESSION_ID_PATTERN.fullmatch(session_id):
            try:
                odoo.destroy_session(session_id)
            except HTTPException:
                pass
        return auth_error_response(error)

    if previous_session_id and SESSION_ID_PATTERN.fullmatch(previous_session_id):
        try:
            odoo.destroy_session(previous_session_id)
        except HTTPException:
            pass
    set_session_cookie(response, session_id)
    return {"success": True, "user": user}


@router.get("/me")
def me(request: Request):
    try:
        session_id = get_cookie_session(request)
        user = get_verified_user(session_id)
    except HTTPException as error:
        return auth_error_response(error)
    return {"success": True, "user": user}


@router.post("/logout")
def logout(request: Request, response: Response):
    require_trusted_origin(request)
    session_id = request.cookies.get(config.AUTH_COOKIE_NAME)
    if session_id and SESSION_ID_PATTERN.fullmatch(session_id):
        try:
            odoo.destroy_session(session_id)
        except HTTPException as error:
            if error.status_code != 401:
                failed = auth_error_response(error)
                return failed
    clear_session_cookie(response)
    return {"success": True, "message": "로그아웃되었습니다."}
