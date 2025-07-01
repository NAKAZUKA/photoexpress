from bot.persistence.order_repo import AbstractOrderRepo


class ListOrdersUC:
    """
    UseCase: вернуть страницу заказов по статусу.
    Логику пагинации и сортировки можем усложнить здесь, не трогая хендлер.
    """

    def __init__(self, order_repo: AbstractOrderRepo, page_size: int = 1) -> None:
        self.order_repo = order_repo
        self.page_size = page_size

    async def __call__(self, *, user_id: int, status: str, page: int):
        return await self.order_repo.list_by_status(
            user_id=user_id,
            status=status,
            limit=self.page_size,
            offset=page * self.page_size,
        )
