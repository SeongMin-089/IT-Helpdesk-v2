from fastapi import APIRouter, HTTPException

from app.constants import CATEGORY_FIELDS
from app.routers import auth
from app.schemas import OcaCategoryCreate, OcaCategoryUpdate
from app.services import assignments, odoo
from app.transformers import transform_categories


router = APIRouter(prefix="/api/oca/categories")


def get_category_record(category_id, active_only=False):
    if category_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="올바르지 않은 문의 유형 번호입니다.",
        )

    domain = [["id", "=", category_id]]
    if active_only:
        domain.append(["active", "=", True])

    records = odoo.search_read(
        model="helpdesk.ticket.category",
        fields=CATEGORY_FIELDS,
        domain=domain,
        limit=1,
        context={"active_test": False},
    )
    if not records:
        raise HTTPException(status_code=404, detail="문의 유형을 찾을 수 없습니다.")
    return records[0]


def category_name_exists(name, parent_id, exclude_id=None):
    domain = [
        ["name", "=", name],
        ["parent_id", "=", parent_id or False],
    ]
    if exclude_id is not None:
        domain.append(["id", "!=", exclude_id])
    return bool(
        odoo.search_read(
            model="helpdesk.ticket.category",
            fields=["id"],
            domain=domain,
            limit=1,
            context={"active_test": False},
        )
    )


def read_categories(include_inactive=False):
    domain = [] if include_inactive else [["active", "=", True]]
    context = {"active_test": False} if include_inactive else None
    records = odoo.search_read(
        model="helpdesk.ticket.category",
        fields=CATEGORY_FIELDS,
        domain=domain,
        limit=100,
        context=context,
    )
    return transform_categories(records)


@router.get("")
def get_oca_categories():
    categories = read_categories()
    return {"success": True, "count": len(categories), "categories": categories}


@router.get("/all")
def get_all_oca_categories():
    auth.require_agent()
    categories = read_categories(include_inactive=True)
    return {"success": True, "count": len(categories), "categories": categories}


@router.post("", status_code=201)
def create_oca_category(data: OcaCategoryCreate):
    auth.require_agent()
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="문의 유형명은 필수입니다.")

    if data.parent_id is not None:
        get_category_record(data.parent_id, active_only=True)
    if category_name_exists(name, data.parent_id):
        raise HTTPException(
            status_code=409,
            detail="동일한 문의 유형이 이미 존재합니다.",
        )
    if data.default_assignee_id is not None:
        assignments.validate_default_assignee(data.default_assignee_id)

    category_id = odoo.create(
        "helpdesk.ticket.category",
        {
            "name": name,
            "parent_id": data.parent_id or False,
            "show_in_portal": data.show_in_portal,
        },
    )[0]
    if data.default_assignee_id is not None:
        assignments.set_category_default_assignee(
            category_id,
            data.default_assignee_id,
        )

    category = transform_categories([get_category_record(category_id)])[0]
    return {
        "success": True,
        "message": "문의 유형이 등록되었습니다.",
        "category": category,
    }


@router.get("/{category_id}")
def get_oca_category_detail(category_id: int):
    category = transform_categories([get_category_record(category_id)])[0]
    return {"success": True, "category": category}


@router.patch("/{category_id}")
def update_oca_category(category_id: int, data: OcaCategoryUpdate):
    auth.require_agent()
    existing = get_category_record(category_id)
    values = {}

    if data.name is not None:
        name = data.name.strip()
        parent_id = (
            data.parent_id
            if "parent_id" in data.model_fields_set
            else (existing["parent_id"][0] if existing.get("parent_id") else None)
        )
        if category_name_exists(name, parent_id, exclude_id=category_id):
            raise HTTPException(
                status_code=409,
                detail="동일한 문의 유형이 이미 존재합니다.",
            )
        values["name"] = name

    if "parent_id" in data.model_fields_set:
        if data.parent_id == category_id:
            raise HTTPException(
                status_code=422,
                detail="자기 자신을 상위 유형으로 지정할 수 없습니다.",
            )
        if data.parent_id is not None:
            get_category_record(data.parent_id, active_only=True)
        target_name = data.name.strip() if data.name is not None else existing["name"]
        if category_name_exists(target_name, data.parent_id, exclude_id=category_id):
            raise HTTPException(
                status_code=409,
                detail="동일한 문의 유형이 이미 존재합니다.",
            )
        values["parent_id"] = data.parent_id or False

    if data.show_in_portal is not None:
        values["show_in_portal"] = data.show_in_portal

    if "default_assignee_id" in data.model_fields_set:
        if data.default_assignee_id is not None:
            assignments.validate_default_assignee(data.default_assignee_id)
        assignments.set_category_default_assignee(
            category_id,
            data.default_assignee_id,
        )

    if values:
        odoo.write("helpdesk.ticket.category", category_id, values)

    category = transform_categories([get_category_record(category_id)])[0]
    return {
        "success": True,
        "message": "문의 유형이 수정되었습니다.",
        "category": category,
    }


def set_category_active(category_id, active):
    category = get_category_record(category_id)
    if bool(category.get("active")) == active:
        action = "복원" if active else "비활성화"
        raise HTTPException(
            status_code=409,
            detail=f"이미 {action}된 문의 유형입니다.",
        )

    odoo.write("helpdesk.ticket.category", category_id, {"active": active})
    updated = get_category_record(category_id)
    if bool(updated.get("active")) != active:
        raise HTTPException(
            status_code=502,
            detail="문의 유형 상태 변경을 확인할 수 없습니다.",
        )
    return transform_categories([updated])[0]


@router.patch("/{category_id}/archive")
def archive_oca_category(category_id: int):
    auth.require_agent()
    return {
        "success": True,
        "message": "문의 유형이 비활성화되었습니다.",
        "category": set_category_active(category_id, False),
    }


@router.patch("/{category_id}/restore")
def restore_oca_category(category_id: int):
    auth.require_agent()
    return {
        "success": True,
        "message": "문의 유형이 활성화되었습니다.",
        "category": set_category_active(category_id, True),
    }
