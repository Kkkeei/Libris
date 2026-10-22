from datetime import date, timedelta


def test_catalog_students_and_classes_are_persisted(client):
    class_response = client.post("/api/v1/classes", json={"name": "Turma de teste", "school_year": date.today().year})
    assert class_response.status_code == 201, class_response.text
    class_id = class_response.json()["id"]

    student_response = client.post("/api/v1/students", json={"full_name": "Aluno de teste", "enrollment_number": "TEST-MAT-001", "class_id": class_id})
    assert student_response.status_code == 201, student_response.text
    assert student_response.json()["class_name"] == "Turma de teste"
    assert len(client.get("/api/v1/students").json()) == 1

    book_response = client.post("/api/v1/books", json={"title": "Livro de teste", "author": "Autor de teste", "category": "Teste", "copies": 2})
    assert book_response.status_code == 201, book_response.text
    assert book_response.json()["copies"] == 2
    assert book_response.json()["available"] == 2
    assert len(client.get("/api/v1/books").json()) == 1


def test_loan_and_return_update_real_availability(client):
    student = client.post("/api/v1/students", json={"full_name": "Aluno empréstimo", "enrollment_number": "TEST-MAT-002"}).json()
    book = client.post("/api/v1/books", json={"title": "Livro empréstimo", "author": "Autor teste", "category": "Teste", "copies": 1}).json()

    loan_response = client.post("/api/v1/loans", json={"student_id": student["id"], "book_id": book["id"], "due_date": str(date.today() + timedelta(days=7))})
    assert loan_response.status_code == 201, loan_response.text
    loan = loan_response.json()
    assert loan["status"] == "active"
    assert client.get("/api/v1/books").json()[0]["available"] == 0

    returned = client.post(f"/api/v1/loans/{loan['id']}/return")
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "returned"
    assert client.get("/api/v1/books").json()[0]["available"] == 1


def test_dashboard_empty_database_returns_zero_counts(client):
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200
    assert response.json() == {"books": 0, "copies": 0, "available_copies": 0, "students": 0, "active_loans": 0, "overdue_loans": 0, "classes": 0}
