from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    isbn: str | None = Field(default=None, max_length=20)
    publisher: str | None = Field(default=None, max_length=160)
    publication_year: int | None = Field(default=None, ge=0, le=2200)
    description: str | None = Field(default=None, max_length=5000)
    copies: int = Field(default=1, ge=1, le=1000)

    @field_validator("title", "author", "category")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Este campo não pode ficar vazio.")
        return normalized


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    author: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    isbn: str | None = Field(default=None, max_length=20)
    publisher: str | None = Field(default=None, max_length=160)
    publication_year: int | None = Field(default=None, ge=0, le=2200)
    description: str | None = Field(default=None, max_length=5000)
    is_active: bool | None = None

    @field_validator("title", "author", "category")
    @classmethod
    def validate_optional_required_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Este campo não pode ficar vazio.")
        return normalized


class BookOut(ORMModel):
    id: int
    title: str
    author: str
    category: str
    isbn: str | None
    publisher: str | None
    publication_year: int | None
    description: str | None
    is_active: bool
    copies: int
    available: int


class StudentCreate(BaseModel):
    enrollment_number: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=2, max_length=160)
    class_id: int | None = None

    @field_validator("enrollment_number", "full_name")
    @classmethod
    def strip_student_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Este campo não pode ficar vazio.")
        return normalized


class StudentUpdate(BaseModel):
    enrollment_number: str | None = Field(default=None, min_length=1, max_length=64)
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    class_id: int | None = None
    is_active: bool | None = None

    @field_validator("enrollment_number", "full_name")
    @classmethod
    def strip_optional_student_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Este campo não pode ficar vazio.")
        return normalized


class StudentOut(ORMModel):
    id: int
    enrollment_number: str
    full_name: str
    class_id: int | None
    is_active: bool
    class_name: str | None


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    school_year: int = Field(ge=2000, le=2200)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Informe o nome da turma.")
        return value


class ClassOut(ORMModel):
    id: int
    name: str
    school_year: int
    is_active: bool
    student_count: int


class LoanCreate(BaseModel):
    student_id: int = Field(gt=0)
    book_id: int = Field(gt=0)
    due_date: date


class LoanOut(BaseModel):
    id: int
    student_id: int
    student: str
    registration: str
    class_name: str | None
    book_id: int
    book: str
    barcode: str
    loaned_at: Any
    due_date: date
    returned_at: Any
    status: str


class LoanRequestCreate(BaseModel):
    book_id: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)


class LoanRequestOut(BaseModel):
    id: int
    student_id: int
    student: str
    registration: str
    book_id: int
    book: str
    status: str
    note: str | None
    requested_at: Any
    resolved_at: Any


class DashboardOut(BaseModel):
    books: int
    copies: int
    available_copies: int
    students: int
    active_loans: int
    overdue_loans: int
    classes: int
