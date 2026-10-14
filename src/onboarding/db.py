from typing import Optional, Sequence

from pydantic import BaseModel
from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.manager import BaseDBManager
from src.onboarding.models import Employee, EmployeeSkill, Proficiency, Skill


class EmployeeDBManager(BaseDBManager[Employee, BaseModel, BaseModel]):
    async def get_by_email(self, db: AsyncSession, *, email: str) -> Optional[Employee]:
        result = await db.execute(select(Employee).where(Employee.email == email))
        return result.scalars().first()

    async def insert_new(self, db: AsyncSession, *, objs_in: Sequence[BaseModel]) -> list[int]:
        if not objs_in:
            return []
        rows = sorted((o.model_dump() for o in objs_in), key=lambda r: r["email"])
        result = await db.execute(
            pg_insert(Employee)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["email"])
            .returning(Employee.id)
        )
        return list(result.scalars().all())

    async def get_for_update(self, db: AsyncSession, *, id: int) -> Optional[Employee]:
        """Fetch an employee holding a row lock until the transaction ends."""
        result = await db.execute(select(Employee).where(Employee.id == id).with_for_update())
        return result.scalars().first()

    async def search(
        self,
        db: AsyncSession,
        *,
        skill: Optional[str],
        min_proficiency: Optional[Proficiency],
        offset: int,
        limit: int,
    ) -> tuple[list[Employee], int]:
        """Page of employees (with all their skills) plus the total match count.
        When both filters are given, a single skill must satisfy both."""
        conditions = []
        if skill is not None or min_proficiency is not None:
            link = (
                select(EmployeeSkill.id)
                .join(Skill, Skill.id == EmployeeSkill.skill_id)
                .where(EmployeeSkill.employee_id == Employee.id)
            )
            if skill is not None:
                link = link.where(func.lower(Skill.name) == skill.strip().lower())
            if min_proficiency is not None:
                link = link.where(
                    EmployeeSkill.proficiency.in_(Proficiency.at_least(min_proficiency))
                )
            conditions.append(exists(link))

        total = await db.scalar(select(func.count()).select_from(Employee).where(*conditions))
        result = await db.execute(
            select(Employee)
            .where(*conditions)
            .options(selectinload(Employee.skills))
            .order_by(Employee.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total or 0


class SkillDBManager(BaseDBManager[Skill, BaseModel, BaseModel]):
    async def get_or_create_many(self, db: AsyncSession, *, names: list[str]) -> dict[str, Skill]:
        """Return {name.lower(): Skill}, creating missing skills. Names match case-insensitively
        (an existing "Python" is reused for "python"). Safe under concurrent calls:
        INSERT .. ON CONFLICT DO NOTHING lets the unique lower(name) index arbitrate, then we
        select. Names are inserted in sorted order so concurrent requests can't deadlock."""
        if not names:
            return {}
        by_key: dict[str, str] = {}
        for n in names:
            by_key.setdefault(n.lower(), n)
        keys = sorted(by_key)
        await db.execute(
            pg_insert(Skill)
            .values([{"name": by_key[k]} for k in keys])
            .on_conflict_do_nothing(index_elements=[func.lower(Skill.name)])
        )
        result = await db.execute(select(Skill).where(func.lower(Skill.name).in_(keys)))
        return {skill.name.lower(): skill for skill in result.scalars()}


class EmployeeSkillDBManager(BaseDBManager[EmployeeSkill, BaseModel, BaseModel]):
    async def delete_for_employee(self, db: AsyncSession, *, employee_id: int) -> None:
        await db.execute(delete(EmployeeSkill).where(EmployeeSkill.employee_id == employee_id))

    async def list_for_employee(self, db: AsyncSession, *, employee_id: int) -> list[EmployeeSkill]:
        result = await db.execute(
            select(EmployeeSkill)
            .where(EmployeeSkill.employee_id == employee_id)
            .order_by(EmployeeSkill.id)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())


employee_manager = EmployeeDBManager(Employee)
skill_manager = SkillDBManager(Skill)
employee_skill_manager = EmployeeSkillDBManager(EmployeeSkill)
