from sqladmin import Admin, ModelView
from starlette.requests import Request
import logging
import json

from .models import Category, Product, Order, OrderItem, OrderStatus, DeliverySlot, AdminAuditLog
from .telegram import notify_order_status
from .db import SessionLocal

logger = logging.getLogger(__name__)

# Valid status transitions
VALID_STATUS_TRANSITIONS = {
    OrderStatus.new: [OrderStatus.accepted, OrderStatus.cancelled],
    OrderStatus.accepted: [OrderStatus.cooking, OrderStatus.cancelled],
    OrderStatus.cooking: [OrderStatus.on_the_way, OrderStatus.cancelled],
    OrderStatus.on_the_way: [OrderStatus.delivered, OrderStatus.cancelled],
    OrderStatus.delivered: [],
    OrderStatus.cancelled: []
}

def log_admin_action(request: Request, action: str, entity_type: str, entity_id: int = None, 
                     old_values: dict = None, new_values: dict = None):
    """Medium Priority Fix: Log admin actions to database"""
    try:
        # Get admin username from basic auth
        auth_header = request.headers.get("authorization", "")
        admin_user = "unknown"
        if auth_header.startswith("Basic "):
            import base64
            try:
                decoded = base64.b64decode(auth_header[6:]).decode()
                admin_user = decoded.split(":")[0]
            except:
                pass
        
        # Get client IP
        ip_address = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
        if "," in ip_address:
            ip_address = ip_address.split(",")[0].strip()
        
        with SessionLocal() as db:
            audit_log = AdminAuditLog(
                admin_user=admin_user,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_values=json.dumps(old_values, default=str) if old_values else None,
                new_values=json.dumps(new_values, default=str) if new_values else None,
                ip_address=ip_address
            )
            db.add(audit_log)
            db.commit()
            
        logger.info(f"Admin action logged: {admin_user} {action} {entity_type} #{entity_id}")
    except Exception as e:
        logger.error(f"Failed to log admin action: {e}")

class CategoryAdmin(ModelView, model=Category):
    column_list = [
        Category.id, 
        Category.name, 
        Category.menu_period, 
        Category.sort, 
        Category.is_active
    ]
    column_sortable_list = [Category.sort, Category.id]
    column_searchable_list = [Category.name]
    form_columns = ["name", "sort", "is_active", "menu_period"]
    name = "Категория"
    name_plural = "Категории"
    icon = "fa-solid fa-folder"
    
    async def on_model_change(self, data: dict, model: Category, is_created: bool, request: Request) -> None:
        action = "create" if is_created else "update"
        log_admin_action(request, action, "Category", model.id, None, data)

class ProductAdmin(ModelView, model=Product):
    column_list = [
        Product.id, 
        Product.name, 
        Product.category_id, 
        Product.menu_period_override, 
        Product.price_rub, 
        Product.is_active
    ]
    column_searchable_list = [Product.name]
    column_sortable_list = [Product.price_rub, Product.id]
    form_columns = [
        "name", 
        "category", 
        "description", 
        "price_rub", 
        "is_active", 
        "photo_url",
        "menu_period_override"
    ]
    name = "Товар"
    name_plural = "Товары"
    icon = "fa-solid fa-utensils"
    
    async def on_model_change(self, data: dict, model: Product, is_created: bool, request: Request) -> None:
        action = "create" if is_created else "update"
        log_admin_action(request, action, "Product", model.id, None, data)

class OrderItemAdmin(ModelView, model=OrderItem):
    column_list = [
        OrderItem.id, 
        OrderItem.order_id, 
        OrderItem.name_snapshot, 
        OrderItem.qty, 
        OrderItem.price_rub_snapshot
    ]
    column_sortable_list = [OrderItem.order_id, OrderItem.qty]
    name = "Позиция заказа"
    name_plural = "Позиции заказов"
    icon = "fa-solid fa-list"
    can_create = False
    can_edit = False
    can_delete = False

class OrderAdmin(ModelView, model=Order):
    column_list = [
        Order.id, 
        Order.created_at, 
        Order.status, 
        Order.total_rub, 
        Order.payment_method, 
        Order.payment_confirmed
    ]
    column_searchable_list = [Order.phone_e164, Order.address]
    column_sortable_list = [Order.created_at, Order.id, Order.total_rub]
    column_filters = [Order.status, Order.payment_method, Order.delivery_mode]
    form_columns = [
        "customer_name",
        "phone_e164",
        "address",
        "status",
        "payment_method",
        "payment_confirmed",
        "delivery_mode",
        "delivery_slot",
        "comment"
    ]
    name = "Заказ"
    name_plural = "Заказы"
    icon = "fa-solid fa-receipt"
    
    async def on_model_change(self, data: dict, model: Order, is_created: bool, request: Request) -> None:
        action = "create" if is_created else "update"
        
        if not is_created and "status" in data:
            old_status = model.status
            new_status = data["status"]
            
            # Validate status transitions
            if not self._is_valid_transition(old_status, new_status):
                raise ValueError(
                    f"Invalid status transition: {old_status.value} -> {new_status.value}"
                )
            
            if old_status != new_status:
                try:
                    await notify_order_status(model.id, new_status.value)
                    logger.info(f"Order {model.id} status changed: {old_status.value} -> {new_status.value}")
                except Exception as e:
                    logger.error(f"Failed to send status notification: {e}")
        
        log_admin_action(request, action, "Order", model.id, None, data)
    
    def _is_valid_transition(self, from_status: OrderStatus, to_status: OrderStatus) -> bool:
        if from_status == to_status:
            return True
        valid_next = VALID_STATUS_TRANSITIONS.get(from_status, [])
        return to_status in valid_next

class DeliverySlotAdmin(ModelView, model=DeliverySlot):
    """Medium Priority Fix: Admin panel for delivery slots"""
    column_list = [
        DeliverySlot.id,
        DeliverySlot.slot_time,
        DeliverySlot.max_orders,
        DeliverySlot.is_active
    ]
    column_sortable_list = [DeliverySlot.slot_time]
    form_columns = ["slot_time", "max_orders", "is_active"]
    name = "Слот доставки"
    name_plural = "Слоты доставки"
    icon = "fa-solid fa-clock"
    
    async def on_model_change(self, data: dict, model: DeliverySlot, is_created: bool, request: Request) -> None:
        action = "create" if is_created else "update"
        log_admin_action(request, action, "DeliverySlot", model.id, None, data)

class AdminAuditLogAdmin(ModelView, model=AdminAuditLog):
    """Medium Priority Fix: View admin audit logs"""
    column_list = [
        AdminAuditLog.id,
        AdminAuditLog.created_at,
        AdminAuditLog.admin_user,
        AdminAuditLog.action,
        AdminAuditLog.entity_type,
        AdminAuditLog.entity_id
    ]
    column_sortable_list = [AdminAuditLog.created_at]
    column_filters = [AdminAuditLog.action, AdminAuditLog.entity_type, AdminAuditLog.admin_user]
    name = "Audit Log"
    name_plural = "Audit Logs"
    icon = "fa-solid fa-clipboard-list"
    can_create = False
    can_edit = False
    can_delete = False

def setup_admin(app, engine):
    admin = Admin(app, engine, title="Sieshka Admin")
    admin.add_view(CategoryAdmin)
    admin.add_view(ProductAdmin)
    admin.add_view(OrderAdmin)
    admin.add_view(OrderItemAdmin)
    admin.add_view(DeliverySlotAdmin)
    admin.add_view(AdminAuditLogAdmin)
    return admin
