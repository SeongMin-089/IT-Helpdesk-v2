from html import escape

from fastapi import APIRouter, HTTPException, Query

from app import config
from app.routers import auth
from app.schemas import OcaFaqCreate, OcaFaqUpdate
from app.services import odoo
from app.transformers import clean_description, oca_relation


router = APIRouter(prefix="/api/oca/faqs")

FAQ_FIELDS = [
    "id",
    "name",
    "content",
    "tag_ids",
    "active",
    "parent_id",
    "type",
    "create_date",
    "write_date",
]


def require_faq_writes():
    auth.require_agent()
    if not config.ODOO_FAQ_WRITE_ENABLED:
        raise HTTPException(
            status_code=403,
            detail=(
                "FAQ 관리 API가 비활성화되어 있습니다. "
                "로컬 개발 설정은 실제 인증·인가를 대체하지 않습니다."
            ),
        )


def _parse_category_id(value, setting_name):
    try:
        category_id = int(value or 0)
    except (TypeError, ValueError):
        category_id = 0
    if category_id <= 0:
        raise HTTPException(
            status_code=500,
            detail=f"{setting_name} 설정이 올바르지 않습니다.",
        )
    return category_id


def get_faq_categories():
    public_id = _parse_category_id(
        config.ODOO_FAQ_PUBLIC_CATEGORY_ID,
        "ODOO_FAQ_PUBLIC_CATEGORY_ID",
    )
    draft_id = _parse_category_id(
        config.ODOO_FAQ_DRAFT_CATEGORY_ID,
        "ODOO_FAQ_DRAFT_CATEGORY_ID",
    )
    if public_id == draft_id:
        raise HTTPException(
            status_code=500,
            detail="FAQ 공개 분류와 초안 분류는 서로 달라야 합니다.",
        )

    records = odoo.search_read(
        model="document.page",
        fields=["id", "name", "type"],
        domain=[["id", "in", [public_id, draft_id]]],
        limit=2,
        context={"active_test": False},
    )
    categories = {record["id"]: record for record in records}
    if (
        set(categories) != {public_id, draft_id}
        or any(record.get("type") != "category" for record in records)
    ):
        raise HTTPException(
            status_code=500,
            detail="FAQ 분류 설정이 document.page category 레코드와 일치하지 않습니다.",
        )
    return {"public": public_id, "draft": draft_id}


def plain_text_to_html(value):
    safe_text = escape(value.strip()).replace("\n", "<br>")
    return f"<p>{safe_text}</p>"


def get_faq_tag_map(records):
    tag_ids = {
        tag_id
        for record in records
        for tag_id in (record.get("tag_ids") or [])
    }
    if not tag_ids:
        return {}
    tags = odoo.search_read(
        model="document.page.tag",
        fields=["id", "name"],
        domain=[["id", "in", list(tag_ids)]],
        limit=len(tag_ids),
        context={"active_test": False},
    )
    return {tag["id"]: tag for tag in tags}


def transform_faq(record, tag_map, categories):
    tags = [
        tag_map[tag_id]
        for tag_id in (record.get("tag_ids") or [])
        if tag_id in tag_map
    ]
    parent_id = oca_relation(record.get("parent_id"))
    parent_record_id = parent_id["id"] if parent_id else None
    return {
        "id": record["id"],
        "name": record.get("name") or "",
        "content": clean_description(record.get("content")),
        "tags": tags,
        "active": bool(record.get("active")),
        "visibility": (
            "public" if parent_record_id == categories["public"] else "draft"
        ),
        "created_at": record.get("create_date"),
        "updated_at": record.get("write_date"),
    }


def transform_faqs(records, categories):
    tag_map = get_faq_tag_map(records)
    return [transform_faq(record, tag_map, categories) for record in records]


def public_faq_domain(public_category_id):
    return [
        ["parent_id", "=", public_category_id],
        ["active", "=", True],
        ["type", "=", "content"],
    ]


def get_managed_faq(faq_id, categories):
    if faq_id <= 0:
        raise HTTPException(status_code=400, detail="올바르지 않은 FAQ 번호입니다.")
    records = odoo.search_read(
        model="document.page",
        fields=FAQ_FIELDS,
        domain=[
            ["id", "=", faq_id],
            ["parent_id", "in", list(categories.values())],
            ["type", "=", "content"],
        ],
        limit=1,
        context={"active_test": False},
    )
    if not records:
        raise HTTPException(status_code=404, detail="FAQ를 찾을 수 없습니다.")
    return records[0]


def validate_tag_ids(tag_ids):
    unique_ids = list(dict.fromkeys(tag_ids))
    if not unique_ids:
        return []
    records = odoo.search_read(
        model="document.page.tag",
        fields=["id"],
        domain=[["id", "in", unique_ids], ["active", "=", True]],
        limit=len(unique_ids),
    )
    if {record["id"] for record in records} != set(unique_ids):
        raise HTTPException(status_code=422, detail="유효하지 않은 FAQ 태그입니다.")
    return unique_ids


def read_faq(faq_id, categories):
    record = get_managed_faq(faq_id, categories)
    return transform_faqs([record], categories)[0]


def create_faq_draft(name, content, tag_ids=None):
    require_faq_writes()
    categories = get_faq_categories()
    valid_tag_ids = validate_tag_ids(tag_ids or [])
    result = odoo.create(
        "document.page",
        {
            "name": name.strip(),
            "content": plain_text_to_html(content),
            "tag_ids": [[6, 0, valid_tag_ids]],
            "active": True,
            "parent_id": categories["draft"],
            "type": "content",
        },
    )
    return read_faq(result[0], categories)


@router.get("/suggestions")
def get_faq_suggestions(q: str = Query(min_length=1, max_length=200)):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="검색어는 필수입니다.")
    categories = get_faq_categories()
    base_domain = public_faq_domain(categories["public"])

    title_records = odoo.search_read(
        "document.page",
        FAQ_FIELDS,
        domain=base_domain + [["name", "ilike", query]],
        limit=20,
    )
    content_records = odoo.search_read(
        "document.page",
        FAQ_FIELDS,
        domain=base_domain + [["content", "ilike", query]],
        limit=20,
    )
    tags = odoo.search_read(
        "document.page.tag",
        ["id", "name"],
        domain=[["name", "ilike", query], ["active", "=", True]],
        limit=20,
    )
    tag_records = []
    if tags:
        tag_records = odoo.search_read(
            "document.page",
            FAQ_FIELDS,
            domain=base_domain + [["tag_ids", "in", [tag["id"] for tag in tags]]],
            limit=20,
        )

    records_by_id = {
        record["id"]: record
        for record in title_records + content_records + tag_records
    }
    records = list(records_by_id.values())
    faqs = transform_faqs(records, categories)
    normalized = query.casefold()

    def score(faq):
        title = faq["name"].casefold()
        tag_names = [tag["name"].casefold() for tag in faq["tags"]]
        return (
            6 if title == normalized else 3 if normalized in title else 0
        ) + (
            4 if normalized in tag_names else 2 if any(
                normalized in tag_name for tag_name in tag_names
            ) else 0
        ) + (1 if normalized in faq["content"].casefold() else 0)

    faqs.sort(key=lambda faq: (-score(faq), faq["name"].casefold(), faq["id"]))
    return {"success": True, "count": min(len(faqs), 3), "faqs": faqs[:3]}


@router.get("/admin/all")
def get_all_faqs():
    require_faq_writes()
    categories = get_faq_categories()
    records = odoo.search_read(
        "document.page",
        FAQ_FIELDS,
        domain=[
            ["parent_id", "in", list(categories.values())],
            ["type", "=", "content"],
        ],
        limit=100,
        context={"active_test": False},
    )
    faqs = transform_faqs(records, categories)
    return {"success": True, "count": len(faqs), "faqs": faqs}


@router.post("/drafts", status_code=201)
def create_faq(data: OcaFaqCreate):
    faq = create_faq_draft(data.name, data.content, data.tag_ids)
    return {"success": True, "message": "FAQ 초안이 생성되었습니다.", "faq": faq}


@router.get("")
def get_public_faqs(limit: int = Query(default=50, ge=1, le=100)):
    categories = get_faq_categories()
    records = odoo.search_read(
        "document.page",
        FAQ_FIELDS,
        domain=public_faq_domain(categories["public"]),
        limit=limit,
    )
    faqs = transform_faqs(records, categories)
    return {"success": True, "count": len(faqs), "faqs": faqs}


@router.get("/{faq_id}")
def get_public_faq(faq_id: int):
    if faq_id <= 0:
        raise HTTPException(status_code=400, detail="올바르지 않은 FAQ 번호입니다.")
    categories = get_faq_categories()
    records = odoo.search_read(
        "document.page",
        FAQ_FIELDS,
        domain=public_faq_domain(categories["public"]) + [["id", "=", faq_id]],
        limit=1,
    )
    if not records:
        raise HTTPException(status_code=404, detail="FAQ를 찾을 수 없습니다.")
    return {
        "success": True,
        "faq": transform_faqs(records, categories)[0],
    }


@router.patch("/{faq_id}")
def update_faq(faq_id: int, data: OcaFaqUpdate):
    require_faq_writes()
    values = {}
    if data.name is not None:
        values["name"] = data.name.strip()
    if data.content is not None:
        values["content"] = plain_text_to_html(data.content)
    if data.tag_ids is not None:
        values["tag_ids"] = [[6, 0, validate_tag_ids(data.tag_ids)]]
    if not values:
        raise HTTPException(
            status_code=422,
            detail="실제로 변경할 FAQ 항목을 하나 이상 입력해야 합니다.",
        )
    categories = get_faq_categories()
    get_managed_faq(faq_id, categories)
    odoo.write("document.page", faq_id, values)
    return {
        "success": True,
        "message": "FAQ가 수정되었습니다.",
        "faq": read_faq(faq_id, categories),
    }


def move_faq(faq_id, target, message):
    require_faq_writes()
    categories = get_faq_categories()
    get_managed_faq(faq_id, categories)
    odoo.write("document.page", faq_id, {"parent_id": categories[target]})
    return {
        "success": True,
        "message": message,
        "faq": read_faq(faq_id, categories),
    }


@router.post("/{faq_id}/publish")
def publish_faq(faq_id: int):
    return move_faq(faq_id, "public", "FAQ가 공개되었습니다.")


@router.post("/{faq_id}/unpublish")
def unpublish_faq(faq_id: int):
    return move_faq(faq_id, "draft", "FAQ가 비공개 초안으로 변경되었습니다.")


def set_faq_active(faq_id, active):
    require_faq_writes()
    categories = get_faq_categories()
    record = get_managed_faq(faq_id, categories)
    if bool(record.get("active")) == active:
        action = "복원" if active else "보관"
        raise HTTPException(status_code=409, detail=f"이미 {action}된 FAQ입니다.")
    odoo.write("document.page", faq_id, {"active": active})
    return {
        "success": True,
        "message": "FAQ가 복원되었습니다." if active else "FAQ가 보관되었습니다.",
        "faq": read_faq(faq_id, categories),
    }


@router.post("/{faq_id}/archive")
def archive_faq(faq_id: int):
    return set_faq_active(faq_id, False)


@router.post("/{faq_id}/restore")
def restore_faq(faq_id: int):
    return set_faq_active(faq_id, True)
