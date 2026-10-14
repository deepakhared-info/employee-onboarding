from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.onboarding.models import Proficiency


class EmployeeCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    start_date: date

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower()


class RowError(BaseModel):
    row: int
    error: str


class EmployeeImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[RowError]


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class EmployeeSkillAssign(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    proficiency: Proficiency

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class EmployeeSkillsSet(BaseModel):
    skills: list[EmployeeSkillAssign]

    @field_validator("skills")
    @classmethod
    def unique_names(cls, v: list[EmployeeSkillAssign]) -> list[EmployeeSkillAssign]:
        names = [a.name for a in v]
        if len(names) != len(set(names)):
            raise ValueError("duplicate skill names in request")
        return v


class EmployeeSkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill: SkillRead
    proficiency: Proficiency


class SkillProficiency(BaseModel):
    name: str
    proficiency: Proficiency


class EmployeeListItem(BaseModel):
    first_name: str
    last_name: str
    email: str
    start_date: date
    skills: list[SkillProficiency]


class EmployeeListResponse(BaseModel):
    items: list[EmployeeListItem]
    page: int
    page_size: int
    total: int
