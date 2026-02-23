from typing import Annotated

from fastapi import APIRouter, status
from fastapi.params import Query

from bdi_api.settings import Settings

settings = Settings()

s5 = APIRouter(
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Something is wrong with the request"},
    },
    prefix="/api/s5",
    tags=["s5"],
)


@s5.post("/db/init")
def init_database() -> str:
    """Create all HR database tables (department, employee, project,
    employee_project, salary_history) with their relationships and indexes.

    Use the BDI_DB_URL environment variable to configure the database connection.
    Default: sqlite:///hr_database.db
    """
    # TODO: Connect to the database using SQLAlchemy or psycopg2
    # TODO: Execute the schema creation SQL (see hr_schema.sql)
    return "OK"


@s5.post("/db/seed")
def seed_database() -> str:
    """Populate the HR database with sample data.

    Inserts departments, employees, projects, assignments, and salary history.
    """
    # TODO: Connect to the database
    # TODO: Execute the seed data SQL (see hr_seed_data.sql)
    return "OK"


@s5.get("/departments/")
def list_departments() -> list[dict]:
    """Return all departments.

    Each department should include: id, name, location
    """
    # TODO: Query all departments and return as list of dicts
    return []


@s5.get("/employees/")
def list_employees(
    page: Annotated[
        int,
        Query(description="Page number (1-indexed)", ge=1),
    ] = 1,
    per_page: Annotated[
        int,
        Query(description="Number of employees per page", ge=1, le=100),
    ] = 10,
) -> list[dict]:
    """Return employees with their department name, paginated.

    Each employee should include: id, first_name, last_name, email, salary, department_name
    """
    # TODO: Query employees with JOIN to department, apply OFFSET and LIMIT
    return []


@s5.get("/departments/{dept_id}/employees")
def list_department_employees(dept_id: int) -> list[dict]:
    """Return all employees in a specific department.

    Each employee should include: id, first_name, last_name, email, salary, hire_date
    """
    # TODO: Query employees filtered by department_id
    return []


@s5.get("/departments/{dept_id}/stats")
def department_stats(dept_id: int) -> dict:
    """Return KPI statistics for a department.

    Response should include: department_name, employee_count, avg_salary, project_count
    """
    # TODO: Calculate department statistics using JOINs and aggregations
    return {}


@s5.get("/employees/{emp_id}/salary-history")
def salary_history(emp_id: int) -> list[dict]:
    """Return the salary evolution for an employee, ordered by date.

    Each entry should include: change_date, old_salary, new_salary, reason
    """
    # TODO: Query salary_history for the given employee, ordered by change_date
    return []
