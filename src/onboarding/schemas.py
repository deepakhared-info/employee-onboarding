from datetime import date

from pydantic import BaseModel, Field, field_validator


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
