from sqladmin import Admin, ModelView
from starlette.requests import Request
from starlette.responses import JSONResponse
from markupsafe import Markup
import logging
import json

from .models import Category, Product, Order, OrderItem, OrderStatus, DeliverySlot, AdminAuditLog
from .telegram import notify_order_status
from .db import SessionLocal, engine

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
        Category.parent,
        Category.menu_period, 
        Category.sort, 
        Category.is_active
    ]
    column_sortable_list = [Category.sort, Category.id]
    column_searchable_list = [Category.name]
    column_filters = [Category.parent_id, Category.menu_period, Category.is_active]
    form_columns = ["name", "parent", "sort", "is_active", "menu_period"]
    name = "Категория"
    name_plural = "Категории"
    icon = "fa-solid fa-folder"
    
    async def on_model_change(self, data: dict, model: Category, is_created: bool, request: Request) -> None:
        action = "create" if is_created else "update"
        
        # Validate self-reference
        parent_id = data.get("parent_id")
        if parent_id and parent_id == model.id:
            raise ValueError("Категория не может быть родителем самой себя")
        
        # Validate circular reference
        if parent_id and not is_created:
            # Check if parent is not a descendant of current category
            if self._is_circular_reference(model, parent_id):
                raise ValueError("Нельзя выбрать дочернюю категорию как родителя (циклическая ссылка)")
        
        log_admin_action(request, action, "Category", model.id, None, data)
    
    def _is_circular_reference(self, category: Category, new_parent_id: int) -> bool:
        """Check if new_parent_id is a descendant of category (circular reference)"""
        from .db import SessionLocal
        
        with SessionLocal() as db:
            current_id = new_parent_id
            visited = set()
            
            while current_id:
                if current_id in visited:
                    break  # Safety check for data inconsistency
                visited.add(current_id)
                
                if current_id == category.id:
                    return True
                
                # Get parent of current category
                parent = db.query(Category).filter(Category.id == current_id).first()
                if not parent:
                    break
                current_id = parent.parent_id
        
        return False

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

def format_status_with_buttons(order: Order) -> str:
    """Format status column with action buttons for valid transitions"""
    current_status = order.status
    valid_next = VALID_STATUS_TRANSITIONS.get(current_status, [])
    
    status_colors = {
        OrderStatus.new: "warning",
        OrderStatus.accepted: "info", 
        OrderStatus.cooking: "primary",
        OrderStatus.on_the_way: "secondary",
        OrderStatus.delivered: "success",
        OrderStatus.cancelled: "danger"
    }
    
    status_labels = {
        OrderStatus.new: "Новый",
        OrderStatus.accepted: "Принят",
        OrderStatus.cooking: "Готовится",
        OrderStatus.on_the_way: "В пути",
        OrderStatus.delivered: "Доставлен",
        OrderStatus.cancelled: "Отменен"
    }
    
    next_labels = {
        OrderStatus.accepted: "Принять",
        OrderStatus.cooking: "Готовить",
        OrderStatus.on_the_way: "В путь",
        OrderStatus.delivered: "Доставлен",
        OrderStatus.cancelled: "Отменить"
    }
    
    color = status_colors.get(current_status, "secondary")
    current_label = status_labels.get(current_status, current_status.value)
    
    html = f'<span class="badge bg-{color}">{current_label}</span>'
    
    if valid_next:
        html += '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;">'
        for next_status in valid_next:
            btn_color = "danger" if next_status == OrderStatus.cancelled else "primary"
            label = next_labels.get(next_status, next_status.value)
            html += f'''
                <button type="button" 
                        style="font-size:11px;padding:2px 6px;"
                        class="btn btn-sm btn-{btn_color}"
                        onclick="if(confirm('Изменить статус заказа #{order.id}?')){{fetch('/admin/api/orders/update-status',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{order_id:{order.id},status:'{next_status.value}'}})}}).then(r=>r.json()).then(d=>{{if(d.success){{this.closest('tr').style.background='#d4edda';setTimeout(()=>location.reload(),300);}}else{{alert('Ошибка: '+d.error);}}}}).catch(e=>alert('Ошибка сети: '+e));}}">
                    {label}
                </button>
            '''
        html += '</div>'
    
    return Markup(html)


def format_payment_with_button(order: Order) -> str:
    """Format payment_confirmed column with toggle button"""
    payment_method_labels = {
        "cash": "Наличные",
        "sbp_transfer": "СБП"
    }
    
    method_label = payment_method_labels.get(order.payment_method.value, order.payment_method.value)
    
    if order.payment_confirmed:
        # Зеленая кнопка - Оплачено
        html = f'''
            <button type="button" 
                    style="font-size:11px;padding:2px 6px;"
                    class="btn btn-sm btn-success"
                    onclick="if(confirm('Отметить заказ #{order.id} как неоплаченный?')){{fetch('/admin/api/orders/update-payment',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{order_id:{order.id},payment_confirmed:false}})}}).then(r=>r.json()).then(d=>{{if(d.success){{this.closest('tr').style.background='#d4edda';setTimeout(()=>location.reload(),300);}}else{{alert('Ошибка: '+d.error);}}}}).catch(e=>alert('Ошибка сети: '+e));}}">
                Оплачено ({method_label})
            </button>
        '''
    else:
        # Красная кнопка - Ожидает оплаты
        html = f'''
            <button type="button" 
                    style="font-size:11px;padding:2px 6px;"
                    class="btn btn-sm btn-danger"
                    onclick="if(confirm('Подтвердить оплату заказа #{order.id}?')){{fetch('/admin/api/orders/update-payment',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{order_id:{order.id},payment_confirmed:true}})}}).then(r=>r.json()).then(d=>{{if(d.success){{this.closest('tr').style.background='#d4edda';setTimeout(()=>location.reload(),300);}}else{{alert('Ошибка: '+d.error);}}}}).catch(e=>alert('Ошибка сети: '+e));}}">
                Ожидает оплаты ({method_label})
            </button>
        '''
    
    return Markup(html)

async def update_order_status_endpoint(request: Request):
    """AJAX endpoint to update order status"""
    try:
        data = await request.json()
        order_id = data.get('order_id')
        new_status_str = data.get('status')
        
        if not order_id or not new_status_str:
            return JSONResponse(
                {"success": False, "error": "Missing order_id or status"},
                status_code=400
            )
        
        with SessionLocal() as db:
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                return JSONResponse(
                    {"success": False, "error": "Order not found"},
                    status_code=404
                )
            
            old_status = order.status
            try:
                new_status = OrderStatus(new_status_str)
            except ValueError:
                return JSONResponse(
                    {"success": False, "error": f"Invalid status: {new_status_str}"},
                    status_code=400
                )
            
            # Validate transition
            valid_next = VALID_STATUS_TRANSITIONS.get(old_status, [])
            if new_status not in valid_next and old_status != new_status:
                return JSONResponse(
                    {"success": False, "error": f"Invalid transition: {old_status.value} -> {new_status.value}"},
                    status_code=400
                )
            
            # Update status
            order.status = new_status
            db.commit()
            
            # Send notification
            if old_status != new_status:
                try:
                    await notify_order_status(order.id, new_status.value)
                except Exception as e:
                    logger.error(f"Failed to send status notification: {e}")
            
            # Log action
            log_admin_action(
                request, 
                "update_status", 
                "Order", 
                order.id,
                {"status": old_status.value},
                {"status": new_status.value}
            )
            
            return JSONResponse({
                "success": True,
                "new_status": new_status.value,
                "order_id": order.id
            })
            
    except Exception as e:
        logger.error(f"Error updating order status: {e}")
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


async def update_payment_status_endpoint(request: Request):
    """AJAX endpoint to update order payment status"""
    try:
        data = await request.json()
        order_id = data.get('order_id')
        payment_confirmed = data.get('payment_confirmed')
        
        if not order_id or payment_confirmed is None:
            return JSONResponse(
                {"success": False, "error": "Missing order_id or payment_confirmed"},
                status_code=400
            )
        
        with SessionLocal() as db:
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                return JSONResponse(
                    {"success": False, "error": "Order not found"},
                    status_code=404
                )
            
            old_payment_status = order.payment_confirmed
            new_payment_status = bool(payment_confirmed)
            
            # Update payment status
            order.payment_confirmed = new_payment_status
            db.commit()
            
            # Send notification if payment confirmed
            if not old_payment_status and new_payment_status:
                try:
                    await notify_order_status(order.id, f"payment_confirmed")
                except Exception as e:
                    logger.error(f"Failed to send payment notification: {e}")
            
            # Log action
            log_admin_action(
                request, 
                "update_payment_status", 
                "Order", 
                order.id,
                {"payment_confirmed": old_payment_status},
                {"payment_confirmed": new_payment_status}
            )
            
            return JSONResponse({
                "success": True,
                "payment_confirmed": new_payment_status,
                "order_id": order.id
            })
            
    except Exception as e:
        logger.error(f"Error updating payment status: {e}")
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )

class OrderAdmin(ModelView, model=Order):
    column_list = [
        Order.id, 
        Order.created_at, 
        Order.status, 
        Order.total_rub, 
        Order.payment_confirmed,
        Order.customer_name
    ]
    column_searchable_list = [Order.phone_e164, Order.address]
    column_sortable_list = [Order.created_at, Order.id, Order.total_rub]
    column_filters = [Order.status, Order.payment_method, Order.delivery_mode]
    column_formatters = {
        Order.status: lambda m, a: format_status_with_buttons(m),
        Order.payment_confirmed: lambda m, a: format_payment_with_button(m)
    }
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
            new_status_str = data["status"]
            
            # Convert string to enum for validation
            try:
                new_status = OrderStatus(new_status_str)
            except ValueError:
                raise ValueError(f"Invalid status value: {new_status_str}")
            
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
