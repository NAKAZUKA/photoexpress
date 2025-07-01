from typing import Protocol
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.database import Order


class AbstractOrderRepo(Protocol):
    async def list_by_status(
        self, user_id: int, status: str, limit: int, offset: int
    ) -> list[Order]: ...


class SqlOrderRepo(AbstractOrderRepo):
    """
    Тонкая обёртка: никакой бизнес-логики — только SQL-запросы.
    """
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_status(
        self, user_id: int, status: str, limit: int, offset: int
    ) -> list[Order]:
        stmt = (
            select(Order)
            .where(Order.user_id == user_id, Order.status == status)
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()
