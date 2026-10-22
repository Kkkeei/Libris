from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    isbn: str | None = Field(default=None, max_length=20)
    publisher: str | None = Field(default=None, max_length=160)
    publication_year: int | None = Field(default=None, ge=0, le=2200)
    description: str | None = None
    copies: int = Field(default=1, ge=1, le=1000)

class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    author: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    isbn: str | None = Field(default=None, max_length=20)
    publisher: str | None = Field(default=None, max_length=160)
    publication_year: int | None = Field(default=None, ge=0, le=2200)
    description: str | None = None
    is_active: bool | None = None

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

class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    school_year: int = Field(ge=2000, le=2200)

class ClassOut(ORMModel):
    id: int
    name: str
    school_year: int
    is_active: bool
    student_count: int = 0

class StudentCreate(BaseModel):
    enrollment_number: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=1, max_length=160)
    class_id: int | None = None

class StudentUpdate(BaseModel):
    enrollment_number: str | None = Field(default=None, min_length=1, max_length=64)
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    class_id: int | None = None
    is_active: bool | None = None

class StudentOut(ORMModel):
    id: int
    enrollment_number: str
    full_name: str
    class_id: int | None
    is_active: bool
    class_name: str | None = None

class LoanCreate(BaseModel):
    student_id: int
    book_id: int
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
    loaned_at: datetime
    due_date: date
    returned_at: datetime | None
    status: str

class DashboardOut(BaseModel):
    books: int
    copies: int
    available_copies: int
    students: int
    active_loans: int
    overdue_loans: int
    classes: int
