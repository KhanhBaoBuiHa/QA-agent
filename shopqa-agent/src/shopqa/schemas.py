"""Schema (pydantic) để kiểm tra JSON mà LLM sinh ra trước khi cho chạy."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

ActionName = Literal[
    "goto", "click", "fill", "select",
    "expect_visible", "expect_not_visible", "expect_text", "expect_url",
    "expect_enabled", "expect_disabled",
]

NEEDS_TARGET = {
    "goto", "click", "fill", "select", "expect_visible", "expect_not_visible",
    "expect_text", "expect_enabled", "expect_disabled",
}
NEEDS_VALUE = {"fill", "select", "expect_text", "expect_url"}
ASSERTIONS = {
    "expect_visible", "expect_not_visible", "expect_text", "expect_url",
    "expect_enabled", "expect_disabled",
}


class ActionModel(BaseModel):
    action: ActionName
    target: Optional[str] = None
    value: Optional[str] = None

    @model_validator(mode="after")
    def check_fields(self):
        if self.action in NEEDS_TARGET and not self.target:
            raise ValueError(f"action '{self.action}' cần có 'target'")
        if self.action in NEEDS_VALUE and self.value is None:
            raise ValueError(f"action '{self.action}' cần có 'value'")
        return self


class TestCaseModel(BaseModel):
    id: str
    title: str
    steps: list[str] = Field(default_factory=list)
    expected: str
    actions: list[ActionModel] = Field(min_length=1)

    @model_validator(mode="after")
    def check_shape(self):
        if self.actions[0].action != "goto":
            raise ValueError(f"test '{self.id}' phải bắt đầu bằng 'goto'")
        if not any(a.action in ASSERTIONS for a in self.actions):
            raise ValueError(f"test '{self.id}' phải có ít nhất một bước expect_*")
        return self


class TestSuiteModel(BaseModel):
    tests: list[TestCaseModel] = Field(min_length=1)

    @model_validator(mode="after")
    def check_unique_ids(self):
        ids = [t.id for t in self.tests]
        if len(ids) != len(set(ids)):
            raise ValueError("id của các test không được trùng nhau")
        return self
