import enum
from datetime import date

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class Proficiency(str, enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

    @classmethod
    def at_least(cls, minimum: "Proficiency") -> list["Proficiency"]:
        """Levels ranked at or above `minimum` (declaration order is the ranking)."""
        levels = list(cls)
        return levels[levels.index(minimum):]


class Employee(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    start_date: Mapped[date]

    skills: Mapped[list["EmployeeSkill"]] = relationship(
        lazy="raise", order_by="EmployeeSkill.id", passive_deletes=True
    )


class Skill(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)


class EmployeeSkill(Base):
    """Association between an employee and a catalog skill, carrying proficiency."""

    __table_args__ = (UniqueConstraint("employee_id", "skill_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skill.id", ondelete="CASCADE"), index=True)
    proficiency: Mapped[Proficiency] = mapped_column(Enum(Proficiency, native_enum=False, length=20))

    skill: Mapped[Skill] = relationship(lazy="joined")
