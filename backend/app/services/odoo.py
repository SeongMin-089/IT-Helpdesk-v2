import requests
from fastapi import HTTPException

from app import config


def _headers():
    return {
        "Authorization": f"Bearer {config.ODOO_API_KEY}",
        "X-Odoo-Database": config.ODOO_DB,
        "Content-Type": "application/json",
    }


def _ensure_api_key():
    if not config.ODOO_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Odoo API key is not configured",
        )


def _session_jsonrpc(path, params, session_id=None, authentication=False):
    cookies = {"session_id": session_id} if session_id else None
    try:
        response = requests.post(
            f"{config.ODOO_URL}{path}",
            headers={"Content-Type": "application/json"},
            cookies=cookies,
            json={"jsonrpc": "2.0", "method": "call", "params": params},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Odoo request timed out")
    except requests.exceptions.HTTPError:
        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=response.status_code,
                detail="Odoo session access denied",
            )
        raise HTTPException(
            status_code=502,
            detail=f"Odoo API error: HTTP {response.status_code}",
        )
    except (requests.exceptions.RequestException, ValueError):
        raise HTTPException(status_code=502, detail="Cannot connect to Odoo")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Invalid Odoo session response")
    error = payload.get("error")
    if error:
        error_data = error.get("data") if isinstance(error, dict) else {}
        error_name = str((error_data or {}).get("name") or "")
        if authentication or "SessionExpired" in error_name or "AccessDenied" in error_name:
            raise HTTPException(status_code=401, detail="Odoo authentication failed")
        if "AccessError" in error_name:
            raise HTTPException(status_code=403, detail="Odoo session access denied")
        raise HTTPException(status_code=502, detail="Odoo session request failed")
    if "result" not in payload:
        raise HTTPException(status_code=502, detail="Invalid Odoo session response")
    return payload["result"], response


def authenticate_session(login, password):
    result, response = _session_jsonrpc(
        "/web/session/authenticate",
        {"db": config.ODOO_DB, "login": login, "password": password},
        authentication=True,
    )
    session_id = response.cookies.get("session_id")
    if not isinstance(result, dict) or not result.get("uid") or not session_id:
        raise HTTPException(status_code=401, detail="Odoo authentication failed")
    return session_id, result


def get_session_info(session_id):
    result, _response = _session_jsonrpc(
        "/web/session/get_session_info",
        {},
        session_id=session_id,
        authentication=True,
    )
    if not isinstance(result, dict) or not result.get("uid"):
        raise HTTPException(status_code=401, detail="Odoo session expired")
    return result


def session_call_kw(session_id, model, method, args=None, kwargs=None):
    result, _response = _session_jsonrpc(
        f"/web/dataset/call_kw/{model}/{method}",
        {
            "model": model,
            "method": method,
            "args": args or [],
            "kwargs": kwargs or {},
        },
        session_id=session_id,
    )
    return result


def destroy_session(session_id):
    _session_jsonrpc(
        "/web/session/destroy",
        {},
        session_id=session_id,
        authentication=True,
    )


def search_read(
    model,
    fields,
    domain=None,
    limit=50,
    context=None,
    order=None,
    offset=0,
):
    _ensure_api_key()
    payload = {
        "domain": domain if domain is not None else [],
        "fields": fields,
        "limit": limit,
        "offset": offset,
    }
    if context is not None:
        payload["context"] = context
    if order is not None:
        payload["order"] = order

    try:
        response = requests.post(
            f"{config.ODOO_URL}/json/2/{model}/search_read",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Odoo request timed out")
    except requests.exceptions.HTTPError:
        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Odoo access denied: HTTP {response.status_code}",
            )
        raise HTTPException(
            status_code=502,
            detail=f"Odoo API error: HTTP {response.status_code}",
        )
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=502, detail="Cannot connect to Odoo")


def search_count(model, domain=None, context=None):
    _ensure_api_key()
    payload = {"domain": domain if domain is not None else []}
    if context is not None:
        payload["context"] = context

    try:
        response = requests.post(
            f"{config.ODOO_URL}/json/2/{model}/search_count",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, int) or isinstance(result, bool) or result < 0:
            raise HTTPException(
                status_code=502,
                detail="Odoo search count returned an unexpected result",
            )
        return result
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Odoo request timed out")
    except requests.exceptions.HTTPError:
        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Odoo access denied: HTTP {response.status_code}",
            )
        raise HTTPException(
            status_code=502,
            detail=f"Odoo API error: HTTP {response.status_code}",
        )
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=502, detail="Cannot connect to Odoo")


def formatted_read_group(model, groupby, aggregates, domain=None):
    _ensure_api_key()
    payload = {
        "domain": domain if domain is not None else [],
        "groupby": groupby,
        "aggregates": aggregates,
    }

    try:
        response = requests.post(
            f"{config.ODOO_URL}/json/2/{model}/formatted_read_group",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, list):
            raise HTTPException(
                status_code=502,
                detail="Odoo grouped read returned an unexpected result",
            )
        return result
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Odoo request timed out")
    except requests.exceptions.HTTPError:
        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Odoo access denied: HTTP {response.status_code}",
            )
        raise HTTPException(
            status_code=502,
            detail=f"Odoo API error: HTTP {response.status_code}",
        )
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=502, detail="Cannot connect to Odoo")


def create(model, values):
    _ensure_api_key()
    try:
        response = requests.post(
            f"{config.ODOO_URL}/json/2/{model}/create",
            headers=_headers(),
            json={"vals_list": [values]},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, list) or len(result) != 1:
            raise HTTPException(
                status_code=502,
                detail="Odoo create returned an unexpected result",
            )
        return result
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Odoo request timed out")
    except requests.exceptions.HTTPError:
        raise HTTPException(
            status_code=502,
            detail=f"Odoo create failed: HTTP {response.status_code}",
        )
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=502, detail="Cannot connect to Odoo")


def write(model, record_id, values):
    _ensure_api_key()
    try:
        response = requests.post(
            f"{config.ODOO_URL}/json/2/{model}/write",
            headers=_headers(),
            json={"ids": [record_id], "vals": values},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        if result is not True:
            raise HTTPException(
                status_code=502,
                detail="Odoo update returned an unexpected result",
            )
        return result
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Odoo request timed out")
    except requests.exceptions.HTTPError:
        raise HTTPException(
            status_code=502,
            detail=f"Odoo update failed: HTTP {response.status_code}",
        )
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=502, detail="Cannot connect to Odoo")


def message_post(
    model,
    record_id,
    body,
    subtype_xmlid="mail.mt_note",
):
    _ensure_api_key()
    try:
        response = requests.post(
            f"{config.ODOO_URL}/json/2/{model}/message_post",
            headers=_headers(),
            json={
                "ids": [record_id],
                "body": body,
                "body_is_html": True,
                "message_type": "comment",
                "subtype_xmlid": subtype_xmlid,
            },
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        if (
            not isinstance(result, list)
            or len(result) != 1
            or not isinstance(result[0], int)
            or result[0] <= 0
        ):
            raise HTTPException(
                status_code=502,
                detail="Odoo message post returned an unexpected result",
            )
        return result[0]
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Odoo request timed out")
    except requests.exceptions.HTTPError:
        raise HTTPException(
            status_code=502,
            detail=f"Odoo message post failed: HTTP {response.status_code}",
        )
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=502, detail="Cannot connect to Odoo")
