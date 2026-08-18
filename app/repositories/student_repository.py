from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.student import Student


class StudentRepository:
    def get_by_code(self, db: Session, student_code: str) -> Student | None:
        return db.execute(
            select(Student).where(Student.student_code == student_code)
        ).scalar_one_or_none()

    def create(
        self,
        db: Session,
        *,
        student_code: str,
        full_name: str,
    ) -> Student:
        student = Student(student_code=student_code, full_name=full_name)
        db.add(student)
        db.commit()
        db.refresh(student)
        return student


student_repository = StudentRepository()
