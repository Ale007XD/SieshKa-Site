from __future__ import annotations

from .models import Order, OrderStatus

# Валидные переходы статусов заказа.
# Ключ — текущий статус, значение — кортеж допустимых следующих.
VALID_STATUS_TRANSITIONS: dict[OrderStatus, tuple[OrderStatus, ...]] = {
    OrderStatus.new:        (OrderStatus.accepted, OrderStatus.cancelled),
    OrderStatus.accepted:   (OrderStatus.cooking,  OrderStatus.cancelled),
    OrderStatus.cooking:    (OrderStatus.on_the_way, OrderStatus.cancelled),
    OrderStatus.on_the_way: (OrderStatus.delivered, OrderStatus.cancelled),
    OrderStatus.delivered:  (),
    OrderStatus.cancelled:  (),
}


def get_next_statuses(status: OrderStatus) -> tuple[OrderStatus, ...]:
    """Возвращает допустимые следующие статусы для данного."""
    return VALID_STATUS_TRANSITIONS.get(status, ())


def is_valid_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
    """True если переход допустим (включая no-op)."""
    if from_status == to_status:
        return True
    return to_status in get_next_statuses(from_status)


def parse_status(value: str) -> OrderStatus:
    """Парсит строку в OrderStatus. Бросает ValueError при неверном значении."""
    return OrderStatus(value)


def update_order_status(order: Order, new_status: OrderStatus) -> tuple[OrderStatus, bool]:
    """
    Обновляет статус заказа с валидацией перехода.

    Returns:
        (old_status, changed) — old_status до изменения, changed=True если статус реально изменился.
    Raises:
        ValueError если переход недопустим.
    """
    old_status = order.status
    if not is_valid_transition(old_status, new_status):
        raise ValueError(
            f"Invalid status transition: {old_status.value} -> {new_status.value}"
        )
    changed = old_status != new_status
    if changed:
        order.status = new_status
    return old_status, changed
