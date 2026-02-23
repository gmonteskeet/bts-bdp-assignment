from fastapi.testclient import TestClient


class TestS5Student:
    """
    Use this class to create your own tests to validate your implementation.

    For more information on testing, search `pytest` and `fastapi.testclient`.
    """

    def test_example(self, client: TestClient) -> None:
        with client as client:
            response = client.post("/api/s5/db/init")
            assert True


class TestItCanBeEvaluated:
    """
    Those tests are just to be sure I can evaluate your exercise.
    Don't modify anything from here!

    Make sure all those tests pass with `pytest` or it will be a 0!
    """

    def test_init_db(self, client: TestClient) -> None:
        with client as client:
            response = client.post("/api/s5/db/init")
            assert not response.is_error, "Error at the db init endpoint"

    def test_seed_db(self, client: TestClient) -> None:
        with client as client:
            response = client.post("/api/s5/db/init")
            response = client.post("/api/s5/db/seed")
            assert not response.is_error, "Error at the db seed endpoint"

    def test_list_departments(self, client: TestClient) -> None:
        with client as client:
            response = client.post("/api/s5/db/init")
            response = client.post("/api/s5/db/seed")
            response = client.get("/api/s5/departments/")
            assert not response.is_error, "Error at the departments endpoint"
            r = response.json()
            assert isinstance(r, list), "Result is not a list"
            assert len(r) > 0, "Result is empty"
            for field in ["id", "name", "location"]:
                assert field in r[0], f"Missing '{field}' field."

    def test_list_employees(self, client: TestClient) -> None:
        with client as client:
            response = client.post("/api/s5/db/init")
            response = client.post("/api/s5/db/seed")
            response = client.get("/api/s5/employees/")
            assert not response.is_error, "Error at the employees endpoint"
            r = response.json()
            assert isinstance(r, list), "Result is not a list"
            assert len(r) > 0, "Result is empty"
            for field in ["id", "first_name", "last_name", "email", "salary", "department_name"]:
                assert field in r[0], f"Missing '{field}' field."

    def test_list_employees_pagination(self, client: TestClient) -> None:
        with client as client:
            response = client.post("/api/s5/db/init")
            response = client.post("/api/s5/db/seed")
            response = client.get("/api/s5/employees/?page=1&per_page=3")
            assert not response.is_error, "Error at the employees pagination"
            r = response.json()
            assert isinstance(r, list), "Result is not a list"
            assert len(r) <= 3, "Pagination not working: returned more than per_page"

    def test_department_employees(self, client: TestClient) -> None:
        with client as client:
            response = client.post("/api/s5/db/init")
            response = client.post("/api/s5/db/seed")
            response = client.get("/api/s5/departments/1/employees")
            assert not response.is_error, "Error at the department employees endpoint"
            r = response.json()
            assert isinstance(r, list), "Result is not a list"
            for field in ["id", "first_name", "last_name", "email", "salary", "hire_date"]:
                if len(r) > 0:
                    assert field in r[0], f"Missing '{field}' field."

    def test_department_stats(self, client: TestClient) -> None:
        with client as client:
            response = client.post("/api/s5/db/init")
            response = client.post("/api/s5/db/seed")
            response = client.get("/api/s5/departments/1/stats")
            assert not response.is_error, "Error at the department stats endpoint"
            r = response.json()
            for field in ["department_name", "employee_count", "avg_salary", "project_count"]:
                assert field in r, f"Missing '{field}' field."

    def test_salary_history(self, client: TestClient) -> None:
        with client as client:
            response = client.post("/api/s5/db/init")
            response = client.post("/api/s5/db/seed")
            response = client.get("/api/s5/employees/1/salary-history")
            assert not response.is_error, "Error at the salary history endpoint"
            r = response.json()
            assert isinstance(r, list), "Result is not a list"
            for field in ["change_date", "old_salary", "new_salary", "reason"]:
                if len(r) > 0:
                    assert field in r[0], f"Missing '{field}' field."
