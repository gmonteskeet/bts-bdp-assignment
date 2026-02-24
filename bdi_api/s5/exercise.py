from typing import Annotated

import os
from fastapi import APIRouter, status, Query
from bdi_api.settings import Settings
from sqlalchemy import create_engine, text

settings = Settings()

s5 = APIRouter(
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Something is wrong with the request"},
    },
    prefix="/api/s5",
    tags=["s5"],
)

def get_engine():
    return create_engine(settings.db_url)

@s5.post("/db/init")
def init_database() -> str:
    """Create all HR database tables (department, employee, project,
    employee_project, salary_history) with their relationships and indexes.

    Use the BDI_DB_URL environment variable to configure the database connection.
    Default: sqlite:///hr_database.db
    """
    engine = get_engine()
    
    sql_path = os.path.join(os.path.dirname(__file__), "sql", "hr_schema.sql")

    with open(sql_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    
    with engine.connect() as conn:
        conn.execute(text(schema_sql))
        conn.commit()
    
    return "OK"


@s5.post("/db/seed")
def seed_database() -> str:
    """Populate the HR database with sample data.

    Inserts departments, employees, projects, assignments, and salary history.
    """
    engine = get_engine()
    
    sql_path = os.path.join(os.path.dirname(__file__), "sql", "hr_seed_data.sql")
    
    with open(sql_path, "r", encoding="utf-8") as f:
        seed_sql = f.read()
    
    with engine.connect() as conn:
        conn.execute(text(seed_sql))
        conn.commit()
    
    return "OK"


@s5.get("/departments/")
def list_departments() -> list[dict]:
    """Return all departments.

    Each department should include: id, name, location
    """
    engine = get_engine()
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, name, location
            FROM department
            ORDER BY id
        """))
        
        departments = [
            {
                "id": row.id,
                "name": row.name,
                "location": row.location
            }
            for row in result
        ]
    
    return departments


@s5.get("/employees/")
def list_employees(
    per_page: int = Query(default=100, ge=1, le=1000),
    page: int = Query(default=0, ge=0)
) -> list[dict]:
    """Return employees with their department name, paginated.

    Each employee should include: id, first_name, last_name, email, salary, department_name
    """
    engine = get_engine()
    offset = page * per_page
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                e.id,
                e.first_name,
                e.last_name,
                e.email,
                e.hire_date,
                e.salary,
                e.department_id,
                d.name as department_name
            FROM employee e
            LEFT JOIN department d ON e.department_id = d.id
            ORDER BY e.id
            LIMIT :limit OFFSET :offset
        """), {"limit": per_page, "offset": offset})
        
        employees = [
            {
                "id": row.id,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "email": row.email,
                "hire_date": str(row.hire_date) if row.hire_date else None,
                "salary": float(row.salary) if row.salary else None,
                "department_id": row.department_id,
                "department_name": row.department_name
            }
            for row in result
        ]
    
    return employees


@s5.get("/departments/{dept_id}/employees")
def list_department_employees(dept_id: int) -> list[dict]:
    """Return all employees in a specific department.

    Each employee should include: id, first_name, last_name, email, salary, hire_date
    """
    engine = get_engine()
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                id,
                first_name,
                last_name,
                email,
                salary,
                hire_date
            FROM employee
            WHERE department_id = :dept_id
            ORDER BY id
        """), {"dept_id": dept_id})
        
        employees = [
            {
                "id": row.id,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "email": row.email,
                "salary": float(row.salary) if row.salary else None,
                "hire_date": str(row.hire_date) if row.hire_date else None
            }
            for row in result
        ]
    
    return employees


@s5.get("/departments/{dept_id}/stats")
def department_stats(dept_id: int) -> dict:
    """Return KPI statistics for a department.

    Response should include: department_name, employee_count, avg_salary, project_count
    """
    engine = get_engine()
    
    with engine.connect() as conn:
        # Get employee stats
        emp_result = conn.execute(text("""
            SELECT 
                d.name as department_name,
                COUNT(e.id) as employee_count,
                AVG(e.salary) as avg_salary
            FROM department d
            LEFT JOIN employee e ON d.id = e.department_id
            WHERE d.id = :dept_id
            GROUP BY d.id, d.name
        """), {"dept_id": dept_id}).fetchone()
        
        # Get project count
        proj_result = conn.execute(text("""
            SELECT COUNT(*) as project_count
            FROM project
            WHERE department_id = :dept_id
        """), {"dept_id": dept_id}).fetchone()
        
    return {
        "department_name": emp_result.department_name if emp_result else None,
        "employee_count": emp_result.employee_count or 0 if emp_result else 0,
        "avg_salary": round(float(emp_result.avg_salary), 2) if emp_result and emp_result.avg_salary else 0,
        "project_count": proj_result.project_count or 0
    }


@s5.get("/employees/{emp_id}/salary-history")
def salary_history(emp_id: int) -> list[dict]:
    """Return the salary evolution for an employee, ordered by date.

    Each entry should include: change_date, old_salary, new_salary, reason
    """
    engine = get_engine()
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                old_salary,
                new_salary,
                change_date,
                reason
            FROM salary_history
            WHERE employee_id = :emp_id
            ORDER BY change_date ASC
        """), {"emp_id": emp_id})
        
        history = [
            {
                "change_date": str(row.change_date),
                "old_salary": float(row.old_salary),
                "new_salary": float(row.new_salary),
                "reason": row.reason
            }
            for row in result
        ]
    
    return history
