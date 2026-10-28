import logging
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user, require_librarian
from app.db.session import get_db
from app.models import Book, BookCopy, Loan, LoanRequest, SchoolClass, Student, StudentAccount, User
from app.schemas.library import (
    BookCreate, BookOut, BookUpdate, ClassCreate, ClassOut, DashboardOut,
    LoanCreate, LoanOut, LoanRequestCreate, LoanRequestOut, StudentCreate, StudentOut, StudentUpdate,
)

logger = logging.getLogger("libris.library")

# Separate routers make public data and administrative operations explicit.
admin_router = APIRouter(tags=["biblioteca"], dependencies=[Depends(require_librarian)])
public_router = APIRouter(tags=["catálogo público"])
student_router = APIRouter(tags=["portal do aluno"])


def _book_out(db: Session, book: Book) -> BookOut:
    copies = db.scalar(
        select(func.count(BookCopy.id)).where(
            BookCopy.book_id == book.id, BookCopy.is_active.is_(True)
        )
    ) or 0
    borrowed = db.scalar(
        select(func.count(Loan.id))
        .join(BookCopy, Loan.copy_id == BookCopy.id)
        .where(
            BookCopy.book_id == book.id,
            BookCopy.is_active.is_(True),
            Loan.returned_at.is_(None),
        )
    ) or 0
    return BookOut(
        id=book.id,
        title=book.title,
        author=book.author,
        category=book.category,
        isbn=book.isbn,
        publisher=book.publisher,
        publication_year=book.publication_year,
        description=book.description,
        is_active=book.is_active,
        copies=copies,
        available=max(copies - borrowed, 0),
    )


def _student_out(student: Student) -> StudentOut:
    return StudentOut(
        id=student.id,
        enrollment_number=student.enrollment_number,
        full_name=student.full_name,
        class_id=student.class_id,
        is_active=student.is_active,
        class_name=student.school_class.name if student.school_class else None,
    )


def _loan_out(loan: Loan) -> LoanOut:
    now_date = date.today()
    status_text = "returned" if loan.returned_at else (
        "overdue" if loan.due_date < now_date else "active"
    )
    return LoanOut(
        id=loan.id,
        student_id=loan.student_id,
        student=loan.student.full_name,
        registration=loan.student.enrollment_number,
        class_name=loan.student.school_class.name if loan.student.school_class else None,
        book_id=loan.copy.book_id,
        book=loan.copy.book.title,
        barcode=loan.copy.barcode,
        loaned_at=loan.loaned_at,
        due_date=loan.due_date,
        returned_at=loan.returned_at,
        status=status_text,
    )


@public_router.get("/books", response_model=list[BookOut])
def list_books(
    q: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Book).where(Book.is_active.is_(True)).order_by(Book.title).limit(200)
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            (Book.title.ilike(term)) | (Book.author.ilike(term)) | (Book.isbn.ilike(term))
        )
    if category and category.strip():
        stmt = stmt.where(Book.category.ilike(category.strip()))
    return [_book_out(db, book) for book in db.scalars(stmt).all()]


@public_router.get("/books/{book_id}", response_model=BookOut)
def get_public_book(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if book is None or not book.is_active:
        raise HTTPException(status_code=404, detail="Livro não encontrado.")
    return _book_out(db, book)


@admin_router.get("/admin/books", response_model=list[BookOut])
def list_admin_books(
    q: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    stmt = select(Book).order_by(Book.title).limit(500)
    if not include_inactive:
        stmt = stmt.where(Book.is_active.is_(True))
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            (Book.title.ilike(term)) | (Book.author.ilike(term)) | (Book.isbn.ilike(term))
        )
    return [_book_out(db, book) for book in db.scalars(stmt).all()]


@admin_router.post("/books", response_model=BookOut, status_code=status.HTTP_201_CREATED)
def create_book(payload: BookCreate, db: Session = Depends(get_db)):
    book = Book(
        title=payload.title.strip(),
        author=payload.author.strip(),
        category=payload.category.strip(),
        isbn=payload.isbn.strip() if payload.isbn else None,
        publisher=payload.publisher,
        publication_year=payload.publication_year,
        description=payload.description,
    )
    db.add(book)
    try:
        db.flush()
        for number in range(1, payload.copies + 1):
            db.add(
                BookCopy(
                    book_id=book.id,
                    barcode=f"LBR-{book.id:06d}-{number:04d}-{uuid4().hex[:4].upper()}",
                )
            )
        db.commit()
        db.refresh(book)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Já existe um livro cadastrado com esse ISBN.") from exc
    return _book_out(db, book)


@admin_router.patch("/books/{book_id}", response_model=BookOut)
def update_book(book_id: int, payload: BookUpdate, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Livro não encontrado.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(book, key, value.strip() if isinstance(value, str) else value)
    try:
        db.commit()
        db.refresh(book)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "ISBN já cadastrado em outro livro.") from exc
    return _book_out(db, book)


@admin_router.get("/students", response_model=list[StudentOut])
def list_students(
    q: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    stmt = (
        select(Student)
        .options(joinedload(Student.school_class))
        .order_by(Student.full_name)
        .limit(500)
    )
    if not include_inactive:
        stmt = stmt.where(Student.is_active.is_(True))
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            (Student.full_name.ilike(term)) | (Student.enrollment_number.ilike(term))
        )
    return [_student_out(s) for s in db.scalars(stmt).unique().all()]


@admin_router.post("/students", response_model=StudentOut, status_code=201)
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    if payload.class_id is not None and not db.get(SchoolClass, payload.class_id):
        raise HTTPException(404, "Turma não encontrada.")
    student = Student(
        enrollment_number=payload.enrollment_number.strip(),
        full_name=payload.full_name.strip(),
        class_id=payload.class_id,
    )
    db.add(student)
    try:
        db.commit()
        db.refresh(student)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Matrícula já cadastrada.") from exc
    student = db.scalar(
        select(Student)
        .options(joinedload(Student.school_class))
        .where(Student.id == student.id)
    )
    return _student_out(student)


@admin_router.patch("/students/{student_id}", response_model=StudentOut)
def update_student(student_id: int, payload: StudentUpdate, db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(404, "Aluno não encontrado.")
    values = payload.model_dump(exclude_unset=True)
    if values.get("class_id") is not None and not db.get(SchoolClass, values["class_id"]):
        raise HTTPException(404, "Turma não encontrada.")
    for key, value in values.items():
        setattr(student, key, value.strip() if isinstance(value, str) else value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Matrícula já cadastrada.") from exc
    student = db.scalar(
        select(Student)
        .options(joinedload(Student.school_class))
        .where(Student.id == student_id)
    )
    return _student_out(student)


@admin_router.get("/classes", response_model=list[ClassOut])
def list_classes(school_year: int | None = None, db: Session = Depends(get_db)):
    stmt = (
        select(SchoolClass)
        .where(SchoolClass.is_active.is_(True))
        .order_by(SchoolClass.school_year.desc(), SchoolClass.name)
        .limit(300)
    )
    if school_year:
        stmt = stmt.where(SchoolClass.school_year == school_year)
    classes = db.scalars(stmt).all()
    return [
        ClassOut(
            id=c.id,
            name=c.name,
            school_year=c.school_year,
            is_active=c.is_active,
            student_count=db.scalar(
                select(func.count(Student.id)).where(
                    Student.class_id == c.id, Student.is_active.is_(True)
                )
            ) or 0,
        )
        for c in classes
    ]


@admin_router.post("/classes", response_model=ClassOut, status_code=201)
def create_class(payload: ClassCreate, db: Session = Depends(get_db)):
    existing = db.scalar(
        select(SchoolClass).where(
            SchoolClass.name == payload.name.strip(),
            SchoolClass.school_year == payload.school_year,
            SchoolClass.is_active.is_(True),
        )
    )
    if existing:
        raise HTTPException(409, "Essa turma já está cadastrada para o ano letivo informado.")
    obj = SchoolClass(name=payload.name.strip(), school_year=payload.school_year)
    db.add(obj)
    try:
        db.commit()
        db.refresh(obj)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Não foi possível cadastrar a turma duplicada.") from exc
    return ClassOut(
        id=obj.id, name=obj.name, school_year=obj.school_year,
        is_active=obj.is_active, student_count=0
    )


@admin_router.get("/loans", response_model=list[LoanOut])
def list_loans(
    q: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Loan)
        .options(
            joinedload(Loan.student).joinedload(Student.school_class),
            joinedload(Loan.copy).joinedload(BookCopy.book),
        )
        .order_by(Loan.loaned_at.desc())
        .limit(1000)
    )
    loans = db.scalars(stmt).unique().all()
    result = [_loan_out(item) for item in loans]
    if q and q.strip():
        term = q.casefold().strip()
        result = [
            item for item in result
            if term in item.student.casefold()
            or term in item.book.casefold()
            or term in item.registration.casefold()
        ]
    if status_filter:
        result = [item for item in result if item.status == status_filter]
    return result


def _available_copy(db: Session, book_id: int) -> BookCopy | None:
    return db.scalar(
        select(BookCopy)
        .where(
            BookCopy.book_id == book_id,
            BookCopy.is_active.is_(True),
            ~BookCopy.loans.any(Loan.returned_at.is_(None)),
        )
        .order_by(BookCopy.id)
        .limit(1)
    )


@admin_router.post("/loans", response_model=LoanOut, status_code=201)
def create_loan(payload: LoanCreate, db: Session = Depends(get_db)):
    student = db.get(Student, payload.student_id)
    if not student or not student.is_active:
        raise HTTPException(404, "Aluno não encontrado ou inativo.")
    book = db.get(Book, payload.book_id)
    if not book or not book.is_active:
        raise HTTPException(404, "Livro não encontrado ou inativo.")
    if payload.due_date < date.today():
        raise HTTPException(422, "A data de devolução não pode estar no passado.")
    copy = _available_copy(db, book.id)
    if copy is None:
        raise HTTPException(409, "Não há exemplares disponíveis deste livro.")
    loan = Loan(student_id=student.id, copy_id=copy.id, due_date=payload.due_date, status="active")
    db.add(loan)
    try:
        db.commit()
        db.refresh(loan)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "O exemplar acabou de ser emprestado. Atualize a lista e tente novamente.") from exc
    saved = db.scalar(
        select(Loan)
        .options(
            joinedload(Loan.student).joinedload(Student.school_class),
            joinedload(Loan.copy).joinedload(BookCopy.book),
        )
        .where(Loan.id == loan.id)
    )
    return _loan_out(saved)


@admin_router.post("/loans/{loan_id}/return", response_model=LoanOut)
def return_loan(loan_id: int, db: Session = Depends(get_db)):
    loan = db.scalar(
        select(Loan)
        .options(
            joinedload(Loan.student).joinedload(Student.school_class),
            joinedload(Loan.copy).joinedload(BookCopy.book),
        )
        .where(Loan.id == loan_id)
    )
    if not loan:
        raise HTTPException(404, "Empréstimo não encontrado.")
    if loan.returned_at:
        raise HTTPException(409, "Este empréstimo já foi devolvido.")
    loan.returned_at = datetime.now(timezone.utc)
    loan.status = "returned"
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to return loan id=%s", loan_id)
        raise HTTPException(503, "Não foi possível confirmar a devolução. Verifique o histórico antes de repetir.") from exc
    saved = db.scalar(
        select(Loan)
        .options(
            joinedload(Loan.student).joinedload(Student.school_class),
            joinedload(Loan.copy).joinedload(BookCopy.book),
        )
        .where(Loan.id == loan_id)
    )
    return _loan_out(saved)


@admin_router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db)):
    today = date.today()
    return DashboardOut(
        books=db.scalar(select(func.count(Book.id)).where(Book.is_active.is_(True))) or 0,
        copies=db.scalar(
            select(func.count(BookCopy.id))
            .join(Book, Book.id == BookCopy.book_id)
            .where(BookCopy.is_active.is_(True), Book.is_active.is_(True))
        ) or 0,
        available_copies=db.scalar(
            select(func.count(BookCopy.id))
            .join(Book, Book.id == BookCopy.book_id)
            .where(
                BookCopy.is_active.is_(True),
                Book.is_active.is_(True),
                ~BookCopy.loans.any(Loan.returned_at.is_(None)),
            )
        ) or 0,
        students=db.scalar(select(func.count(Student.id)).where(Student.is_active.is_(True))) or 0,
        active_loans=db.scalar(select(func.count(Loan.id)).where(Loan.returned_at.is_(None))) or 0,
        overdue_loans=db.scalar(
            select(func.count(Loan.id)).where(Loan.returned_at.is_(None), Loan.due_date < today)
        ) or 0,
        classes=db.scalar(select(func.count(SchoolClass.id)).where(SchoolClass.is_active.is_(True))) or 0,
    )


@student_router.get("/students/me/loans", response_model=list[LoanOut])
def my_loans(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Esta área é exclusiva dos alunos.")
    link = db.scalar(select(StudentAccount).where(StudentAccount.user_id == current_user.id))
    if link is None:
        raise HTTPException(status_code=404, detail="Este acesso não está vinculado a um aluno.")
    stmt = (
        select(Loan)
        .options(
            joinedload(Loan.student).joinedload(Student.school_class),
            joinedload(Loan.copy).joinedload(BookCopy.book),
        )
        .where(Loan.student_id == link.student_id)
        .order_by(Loan.loaned_at.desc())
        .limit(200)
    )
    return [_loan_out(loan) for loan in db.scalars(stmt).unique().all()]


def _loan_request_out(request_obj: LoanRequest) -> LoanRequestOut:
    return LoanRequestOut(
        id=request_obj.id,
        student_id=request_obj.student_id,
        student=request_obj.student.full_name,
        registration=request_obj.student.enrollment_number,
        book_id=request_obj.book_id,
        book=request_obj.book.title,
        status=request_obj.status,
        note=request_obj.note,
        requested_at=request_obj.requested_at,
        resolved_at=request_obj.resolved_at,
    )


@student_router.get("/students/me/loan-requests", response_model=list[LoanRequestOut])
def my_loan_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Esta área é exclusiva dos alunos.")
    link = db.scalar(select(StudentAccount).where(StudentAccount.user_id == current_user.id))
    if link is None:
        raise HTTPException(status_code=404, detail="Este acesso não está vinculado a um aluno.")
    stmt = (
        select(LoanRequest)
        .options(joinedload(LoanRequest.student), joinedload(LoanRequest.book))
        .where(LoanRequest.student_id == link.student_id)
        .order_by(LoanRequest.requested_at.desc())
        .limit(100)
    )
    return [_loan_request_out(item) for item in db.scalars(stmt).unique().all()]


@student_router.post(
    "/students/me/loan-requests",
    response_model=LoanRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_my_loan_request(
    payload: LoanRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Esta área é exclusiva dos alunos.")
    link = db.scalar(select(StudentAccount).where(StudentAccount.user_id == current_user.id))
    if link is None:
        raise HTTPException(status_code=404, detail="Este acesso não está vinculado a um aluno.")
    student = db.get(Student, link.student_id)
    if student is None or not student.is_active:
        raise HTTPException(status_code=404, detail="Cadastro de aluno inativo ou não encontrado.")
    book = db.get(Book, payload.book_id)
    if book is None or not book.is_active:
        raise HTTPException(status_code=404, detail="Livro não encontrado ou inativo.")
    if _available_copy(db, book.id) is None:
        raise HTTPException(status_code=409, detail="Não há exemplares disponíveis desse livro no momento.")
    pending = db.scalar(
        select(LoanRequest.id).where(
            LoanRequest.student_id == student.id,
            LoanRequest.book_id == book.id,
            LoanRequest.status == "pending",
        )
    )
    if pending is not None:
        raise HTTPException(status_code=409, detail="Você já possui uma solicitação pendente para esse livro.")
    request_obj = LoanRequest(
        student_id=student.id,
        book_id=book.id,
        status="pending",
        note=payload.note.strip() if payload.note and payload.note.strip() else None,
    )
    db.add(request_obj)
    try:
        db.commit()
        db.refresh(request_obj)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A solicitação já foi registrada. Atualize a lista antes de tentar novamente.") from exc
    saved = db.scalar(
        select(LoanRequest)
        .options(joinedload(LoanRequest.student), joinedload(LoanRequest.book))
        .where(LoanRequest.id == request_obj.id)
    )
    return _loan_request_out(saved)


@admin_router.get("/loan-requests", response_model=list[LoanRequestOut])
def list_loan_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    stmt = (
        select(LoanRequest)
        .options(joinedload(LoanRequest.student), joinedload(LoanRequest.book))
        .order_by(LoanRequest.requested_at.desc())
        .limit(500)
    )
    requests = db.scalars(stmt).unique().all()
    if status_filter:
        requests = [item for item in requests if item.status == status_filter]
    return [_loan_request_out(item) for item in requests]


@admin_router.post("/loan-requests/{request_id}/confirm", response_model=LoanOut)
def confirm_loan_request(
    request_id: int,
    current_user: User = Depends(require_librarian),
    db: Session = Depends(get_db),
):
    request_obj = db.scalar(
        select(LoanRequest)
        .options(joinedload(LoanRequest.student), joinedload(LoanRequest.book))
        .where(LoanRequest.id == request_id)
    )
    if request_obj is None:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if request_obj.status != "pending":
        raise HTTPException(status_code=409, detail="Esta solicitação já foi resolvida.")
    student = db.get(Student, request_obj.student_id)
    book = db.get(Book, request_obj.book_id)
    if student is None or not student.is_active or book is None or not book.is_active:
        raise HTTPException(status_code=409, detail="Aluno ou livro inativo; a solicitação não pode ser confirmada.")
    # Atomically claim the pending request. A concurrent confirmation cannot also win.
    from sqlalchemy import update
    claim = db.execute(
        update(LoanRequest)
        .where(LoanRequest.id == request_id, LoanRequest.status == "pending")
        .values(
            status="approved",
            resolved_at=datetime.now(timezone.utc),
            resolved_by_user_id=current_user.id,
        )
    )
    if claim.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Esta solicitação já foi resolvida por outra operação.")
    copy = _available_copy(db, book.id)
    if copy is None:
        db.rollback()
        raise HTTPException(status_code=409, detail="Não há exemplares disponíveis. A solicitação continua pendente.")
    loan = Loan(
        student_id=student.id,
        copy_id=copy.id,
        due_date=date.today() + timedelta(days=7),
        status="active",
        created_by_user_id=current_user.id,
    )
    db.add(loan)
    try:
        db.commit()
        db.refresh(loan)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="O exemplar acabou de ser emprestado. Atualize as solicitações.") from exc
    saved = db.scalar(
        select(Loan)
        .options(
            joinedload(Loan.student).joinedload(Student.school_class),
            joinedload(Loan.copy).joinedload(BookCopy.book),
        )
        .where(Loan.id == loan.id)
    )
    return _loan_out(saved)


@admin_router.post("/loan-requests/{request_id}/reject", response_model=LoanRequestOut)
def reject_loan_request(
    request_id: int,
    current_user: User = Depends(require_librarian),
    db: Session = Depends(get_db),
):
    request_obj = db.scalar(
        select(LoanRequest)
        .options(joinedload(LoanRequest.student), joinedload(LoanRequest.book))
        .where(LoanRequest.id == request_id)
    )
    if request_obj is None:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if request_obj.status != "pending":
        raise HTTPException(status_code=409, detail="Esta solicitação já foi resolvida.")
    request_obj.status = "rejected"
    request_obj.resolved_at = datetime.now(timezone.utc)
    request_obj.resolved_by_user_id = current_user.id
    try:
        db.commit()
        db.refresh(request_obj)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Não foi possível registrar a decisão.") from exc
    saved = db.scalar(
        select(LoanRequest)
        .options(joinedload(LoanRequest.student), joinedload(LoanRequest.book))
        .where(LoanRequest.id == request_obj.id)
    )
    return _loan_request_out(saved)
