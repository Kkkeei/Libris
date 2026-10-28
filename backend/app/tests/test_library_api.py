from datetime import date, timedelta

from app.core.security import hash_password
from app.models import User


def _create_librarian(db_session):
    user = User(
        email="bibliotecaria@example.test",
        full_name="Bibliotecária de teste",
        password_hash=hash_password("Senha-de-teste-segura-2026"),
        role="librarian",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _admin_headers(client, db_session):
    _create_librarian(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "bibliotecaria@example.test", "password": "Senha-de-teste-segura-2026"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_catalog_students_and_classes_are_persisted(client, db_session):
    headers = _admin_headers(client, db_session)
    class_response = client.post("/api/v1/classes", headers=headers, json={"name": "Turma de teste", "school_year": date.today().year})
    assert class_response.status_code == 201, class_response.text
    class_id = class_response.json()["id"]

    student_response = client.post("/api/v1/students", headers=headers, json={"full_name": "Aluno de teste", "enrollment_number": "TEST-MAT-001", "class_id": class_id})
    assert student_response.status_code == 201, student_response.text
    assert student_response.json()["class_name"] == "Turma de teste"
    assert len(client.get("/api/v1/students", headers=headers).json()) == 1
    assert client.get("/api/v1/students").status_code == 401

    book_response = client.post("/api/v1/books", headers=headers, json={"title": "Livro de teste", "author": "Autor de teste", "category": "Teste", "copies": 2})
    assert book_response.status_code == 201, book_response.text
    assert book_response.json()["copies"] == 2
    assert book_response.json()["available"] == 2
    assert len(client.get("/api/v1/books").json()) == 1


def test_loan_and_return_update_real_availability(client, db_session):
    headers = _admin_headers(client, db_session)
    student = client.post("/api/v1/students", headers=headers, json={"full_name": "Aluno empréstimo", "enrollment_number": "TEST-MAT-002"}).json()
    book = client.post("/api/v1/books", headers=headers, json={"title": "Livro empréstimo", "author": "Autor teste", "category": "Teste", "copies": 1}).json()

    payload = {"student_id": student["id"], "book_id": book["id"], "due_date": str(date.today() + timedelta(days=7))}
    loan_response = client.post("/api/v1/loans", headers=headers, json=payload)
    assert loan_response.status_code == 201, loan_response.text
    loan = loan_response.json()
    assert loan["status"] == "active"
    assert client.get("/api/v1/books").json()[0]["available"] == 0
    duplicate = client.post("/api/v1/loans", headers=headers, json=payload)
    assert duplicate.status_code == 409

    returned = client.post(f"/api/v1/loans/{loan['id']}/return", headers=headers)
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "returned"
    assert client.get("/api/v1/books").json()[0]["available"] == 1


def test_dashboard_requires_authentication(client):
    assert client.get("/api/v1/dashboard").status_code == 401
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_student_can_only_read_own_loan_history(client, db_session):
    headers = _admin_headers(client, db_session)
    first = client.post("/api/v1/students", headers=headers, json={"full_name": "Primeiro aluno", "enrollment_number": "TEST-MAT-101"}).json()
    client.post("/api/v1/students", headers=headers, json={"full_name": "Segundo aluno", "enrollment_number": "TEST-MAT-102"})
    account = client.post(
        "/api/v1/auth/student-accounts",
        headers=headers,
        json={"student_id": first["id"], "username": "aluno101", "password": "Senha-aluno-forte-2026"},
    )
    assert account.status_code == 201, account.text
    login = client.post("/api/v1/auth/login", json={"username": "aluno101", "password": "Senha-aluno-forte-2026"})
    assert login.status_code == 200, login.text
    student_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/students/me/loans", headers=student_headers).json() == []
    assert client.get("/api/v1/students", headers=student_headers).status_code == 403


def test_student_loan_request_stays_pending_until_librarian_confirms(client, db_session):
    admin_headers = _admin_headers(client, db_session)
    student = client.post(
        "/api/v1/students",
        headers=admin_headers,
        json={"full_name": "Aluna solicitante", "enrollment_number": "TEST-REQ-001"},
    ).json()
    book = client.post(
        "/api/v1/books",
        headers=admin_headers,
        json={"title": "Livro solicitado", "author": "Autoria de teste", "category": "Teste", "copies": 1},
    ).json()
    account = client.post(
        "/api/v1/auth/student-accounts",
        headers=admin_headers,
        json={"student_id": student["id"], "username": "aluna001", "password": "Senha-aluna-segura-2026"},
    )
    assert account.status_code == 201, account.text
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "aluna001", "password": "Senha-aluna-segura-2026"},
    )
    assert login.status_code == 200, login.text
    student_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    request = client.post(
        "/api/v1/students/me/loan-requests",
        headers=student_headers,
        json={"book_id": book["id"]},
    )
    assert request.status_code == 201, request.text
    assert request.json()["status"] == "pending"
    assert client.get("/api/v1/books").json()[0]["available"] == 1

    duplicate = client.post(
        "/api/v1/students/me/loan-requests",
        headers=student_headers,
        json={"book_id": book["id"]},
    )
    assert duplicate.status_code == 409

    pending = client.get("/api/v1/loan-requests?status=pending", headers=admin_headers)
    assert pending.status_code == 200, pending.text
    assert len(pending.json()) == 1
    confirmed = client.post(
        f"/api/v1/loan-requests/{request.json()['id']}/confirm",
        headers=admin_headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "active"
    assert client.get("/api/v1/books").json()[0]["available"] == 0

    my_requests = client.get("/api/v1/students/me/loan-requests", headers=student_headers)
    assert my_requests.status_code == 200
    assert my_requests.json()[0]["status"] == "approved"
    duplicate_confirmation = client.post(
        f"/api/v1/loan-requests/{request.json()['id']}/confirm",
        headers=admin_headers,
    )
    assert duplicate_confirmation.status_code == 409


def test_archived_books_are_private_to_admin_but_history_is_preserved(client, db_session):
    headers = _admin_headers(client, db_session)
    book = client.post(
        "/api/v1/books",
        headers=headers,
        json={"title": "Livro arquivado", "author": "Autor", "category": "Teste", "copies": 1},
    ).json()
    archived = client.patch(
        f"/api/v1/books/{book['id']}",
        headers=headers,
        json={"is_active": False},
    )
    assert archived.status_code == 200, archived.text
    assert client.get("/api/v1/books").json() == []
    admin_list = client.get("/api/v1/admin/books?include_inactive=true", headers=headers)
    assert admin_list.status_code == 200, admin_list.text
    assert len(admin_list.json()) == 1
    assert admin_list.json()[0]["is_active"] is False


def test_first_librarian_setup_is_one_time(client):
    payload = {
        "email": "primeira.bibliotecaria@example.com",
        "full_name": "Primeira Bibliotecária",
        "password": "Senha-inicial-bem-segura-2026",
        "setup_key": "test-only-setup-key-longer-than-24-chars",
    }
    response = client.post("/api/v1/setup/admin", json=payload)
    assert response.status_code == 201, response.text
    login = client.post(
        "/api/v1/auth/login",
        json={"username": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 200, login.text
    second_attempt = client.post("/api/v1/setup/admin", json=payload)
    assert second_attempt.status_code == 409
