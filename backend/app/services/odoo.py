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


def search_read(model, fields, domain=None, limit=50, context=None):
    _ensure_api_key()
    payload = {
        "domain": domain if domain is not None else [],
        "fields": fields,
        "limit": limit,
    }
    if context is not None:
        payload["context"] = context

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


def message_post(model, record_id, body):
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
                "subtype_xmlid": "mail.mt_note",
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
