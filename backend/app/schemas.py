from pydantic import BaseModel, Field, model_validator

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
