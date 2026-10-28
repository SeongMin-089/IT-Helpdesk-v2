from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from app.constants import OCA_PRIORITY_PATTERN


class OcaCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: int | None = Field(default=None, gt=0)
    show_in_portal: bool = True
    default_assignee_id: int | None = Field(default=None, gt=0)


class OcaCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    parent_id: int | None = Field(default=None, gt=0)
    show_in_portal: bool | None = None
    default_assignee_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("수정할 항목을 하나 이상 입력해야 합니다.")
        if self.name is not None and not self.name.strip():
            raise ValueError("문의 유형명은 비워둘 수 없습니다.")
        return self


class OcaTicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    priority: str = Field(default="1", pattern=OCA_PRIORITY_PATTERN)
    category_id: int | None = Field(default=None, gt=0)


class OcaTicketUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    priority: str | None = Field(default=None, pattern=OCA_PRIORITY_PATTERN)
    assignee_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("수정할 항목을 하나 이상 입력해야 합니다.")
        if self.title is not None and not self.title.strip():
            raise ValueError("제목은 비워둘 수 없습니다.")
        if self.description is not None and not self.description.strip():
            raise ValueError("내용은 비워둘 수 없습니다.")
        return self


class OcaTicketStageUpdate(BaseModel):
    stage_id: int = Field(gt=0)


class OcaTicketResolve(BaseModel):
    resolution: str = Field(min_length=1, max_length=10000)

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value):
        if not value.strip():
            raise ValueError("해결 내용은 필수입니다.")
        return value.strip()


class OcaTicketReprocess(BaseModel):
    reason: str = Field(min_length=1, max_length=10000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value):
        if not value.strip():
            raise ValueError("재처리 사유는 필수입니다.")
        return value.strip()


class OcaTicketCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    kind: Literal["comment", "note"] = "comment"

    @field_validator("body")
    @classmethod
    def validate_body(cls, value):
        if not value.strip():
            raise ValueError("댓글 내용은 필수입니다.")
        return value.strip()


class OcaFaqCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20000)
    tag_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_create(self):
        if not self.name.strip():
            raise ValueError("FAQ 제목은 필수입니다.")
        if not self.content.strip():
            raise ValueError("FAQ 내용은 필수입니다.")
        if any(tag_id <= 0 for tag_id in self.tag_ids):
            raise ValueError("태그 번호는 양수여야 합니다.")
        return self


class OcaFaqUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, max_length=20000)
    tag_ids: list[int] | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("수정할 항목을 하나 이상 입력해야 합니다.")
        if self.name is not None and not self.name.strip():
            raise ValueError("FAQ 제목은 비워둘 수 없습니다.")
        if self.content is not None and not self.content.strip():
            raise ValueError("FAQ 내용은 비워둘 수 없습니다.")
        if self.tag_ids is not None and any(tag_id <= 0 for tag_id in self.tag_ids):
            raise ValueError("태그 번호는 양수여야 합니다.")
        return self


class AuthLogin(BaseModel):
    login: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("login")
    @classmethod
    def validate_login(cls, value):
        login = value.strip()
        if not login:
            raise ValueError("로그인 ID는 필수입니다.")
        return login
