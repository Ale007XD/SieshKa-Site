from sqladmin import Admin, ModelView, action
from sqladmin.filters import BooleanFilter, AllUniqueStringValuesFilter, ForeignKeyFilter
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, HTMLResponse
from markupsafe import Markup
import logging
import json
import csv
import io
from typing import List, Dict, Any

from .models import Category, Product, Order, OrderItem, OrderStatus, DeliverySlot, AdminAuditLog
from .availability_models import AvailabilityRule, MenuConfiguration
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

def log_admin_action(request: Request, action: str, entity_type: str, entity_id: int | None = None, 
                     old_values: dict | None = None, new_values: dict | None = None):
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
    column_filters = [
        BooleanFilter(Category.is_active),
        AllUniqueStringValuesFilter(Category.menu_period),
    ]
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
    column_filters = [
        BooleanFilter(Product.is_active),
        AllUniqueStringValuesFilter(Product.menu_period_override),
        ForeignKeyFilter(Product.category_id, Category.name, title="Категория"),
    ]
    column_formatters = {
        Product.is_active: lambda m, a: format_product_active_button(m)
    }
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
    
    # Массовые действия
    
    @action(
        name="bulk_activate",
        label="Активировать",
        confirmation_message="Активировать выбранные товары?",
        add_in_list=True,
        add_in_detail=False
    )
    async def bulk_activate(self, request: Request):
        """Массовая активация товаров"""
        pks_str = request.query_params.get("pks", "")
        pks = [pk for pk in pks_str.split(",") if pk]
        
        if pks:
            with SessionLocal() as db:
                db.query(Product).filter(Product.id.in_([int(pk) for pk in pks])).update(
                    {Product.is_active: True}, synchronize_session=False
                )
                db.commit()
                log_admin_action(request, "bulk_activate", "Product", None, {"count": len(pks)}, {"pks": pks})
        
        referer = request.headers.get("Referer")
        if referer:
            return RedirectResponse(referer)
        return RedirectResponse(request.url_for("admin:list", identity=self.identity))
    
    @action(
        name="bulk_deactivate",
        label="Деактивировать",
        confirmation_message="Деактивировать выбранные товары?",
        add_in_list=True,
        add_in_detail=False
    )
    async def bulk_deactivate(self, request: Request):
        """Массовая деактивация товаров"""
        pks_str = request.query_params.get("pks", "")
        pks = [pk for pk in pks_str.split(",") if pk]
        
        if pks:
            with SessionLocal() as db:
                db.query(Product).filter(Product.id.in_([int(pk) for pk in pks])).update(
                    {Product.is_active: False}, synchronize_session=False
                )
                db.commit()
                log_admin_action(request, "bulk_deactivate", "Product", None, {"count": len(pks)}, {"pks": pks})
        
        referer = request.headers.get("Referer")
        if referer:
            return RedirectResponse(referer)
        return RedirectResponse(request.url_for("admin:list", identity=self.identity))
    
    @action(
        name="bulk_move_category",
        label="Перенести в категорию",
        add_in_list=True,
        add_in_detail=False
    )
    async def bulk_move_category(self, request: Request):
        """Массовый перенос товаров в другую категорию"""
        pks_str = request.query_params.get("pks", "")
        pks = [pk for pk in pks_str.split(",") if pk]
        
        if not pks:
            return RedirectResponse(request.url_for("admin:list", identity=self.identity))
        
        # Обработка POST-запроса
        if request.method == "POST":
            form_data = await request.form()
            target_category_id = form_data.get("target_category_id")
            
            if target_category_id:
                cat_id = int(target_category_id)
                with SessionLocal() as db:
                    db.query(Product).filter(Product.id.in_([int(pk) for pk in pks])).update(
                        {Product.category_id: cat_id}, synchronize_session=False
                    )
                    db.commit()
                    log_admin_action(request, "bulk_move_category", "Product", None, {"count": len(pks)}, {"new_cat": cat_id})
                
                return RedirectResponse(request.url_for("admin:list", identity=self.identity))
        
        # Показ формы выбора категории
        with SessionLocal() as db:
            categories = db.query(Category).filter(Category.is_active == True).order_by(Category.name).all()
            category_options = "\n".join([
                f'<option value="{cat.id}">{cat.name}</option>' 
                for cat in categories
            ])
            
            html = f'''
            <div class="modal-body">
                <form method="POST">
                    <input type="hidden" name="pks" value="{",".join(pks)}">
                    <div class="mb-3">
                        <label class="form-label">Выберите категорию для {len(pks)} товаров:</label>
                        <select class="form-select" name="target_category_id" required>
                            <option value="">-- Выберите --</option>
                            {category_options}
                        </select>
                    </div>
                    <div class="modal-footer">
                        <button type="submit" class="btn btn-primary">Перенести</button>
                    </div>
                </form>
            </div>
            '''
            return html
    
    async def on_model_change(self, data: dict, model: Product, is_created: bool, request: Request) -> None:
        action = "create" if is_created else "update"
        log_admin_action(request, action, "Product", model.id, None, data)
    
    @action(
        name="import_products",
        label="Импорт из CSV",
        add_in_list=True,
        add_in_detail=False
    )
    async def import_products(self, request: Request):
        """Импорт товаров из CSV файла"""
        if request.method == "POST":
            from starlette.datastructures import UploadFile
            
            form_data = await request.form()
            uploaded_file = form_data.get("csv_file")
            default_category_id = form_data.get("default_category_id")
            skip_errors = form_data.get("skip_errors") == "on"
            
            if not uploaded_file or not isinstance(uploaded_file, UploadFile):
                return HTMLResponse(content="""
                <div class="alert alert-danger">Файл не загружен</div>
                <a href="javascript:history.back()" class="btn btn-secondary">Назад</a>
                """, status_code=400)
            
            # Читаем CSV
            try:
                content = await uploaded_file.read()
                csv_text = content.decode('utf-8-sig')
                csv_reader = csv.DictReader(io.StringIO(csv_text))
            except Exception as e:
                return HTMLResponse(content=f"""
                <div class="alert alert-danger">Ошибка чтения CSV: {str(e)}</div>
                <a href="javascript:history.back()" class="btn btn-secondary">Назад</a>
                """, status_code=400)
            
            # Проверяем обязательное поле Name
            fieldnames = csv_reader.fieldnames or []
            fieldnames_lower = [f.lower().strip() for f in fieldnames]
            
            if 'name' not in fieldnames_lower:
                return HTMLResponse(content="""
                <div class="alert alert-danger">CSV файл должен содержать колонку 'Name'</div>
                <a href="javascript:history.back()" class="btn btn-secondary">Назад</a>
                """, status_code=400)
            
            # Импортируем товары
            results = {"created": 0, "errors": [], "skipped": 0}
            
            with SessionLocal() as db:
                # Кэш категорий
                categories_cache = {}
                
                for row_num, row in enumerate(csv_reader, start=2):  # start=2 потому что первая строка - заголовки
                    try:
                        # Получаем значения полей (регистронезависимо)
                        row_lower = {k.lower().strip(): v.strip() if v else None for k, v in row.items()}
                        
                        name = row_lower.get('name', '').strip()
                        if not name:
                            if skip_errors:
                                results["skipped"] += 1
                                continue
                            else:
                                results["errors"].append(f"Строка {row_num}: отсутствует Name")
                                continue
                        
                        # Категория: по ID или по названию
                        category_id = None
                        category_value = row_lower.get('category', '').strip()
                        
                        if category_value:
                            if category_value.isdigit():
                                category_id = int(category_value)
                            else:
                                # Ищем по названию
                                if category_value not in categories_cache:
                                    cat = db.query(Category).filter(
                                        Category.name.ilike(category_value)
                                    ).first()
                                    if cat:
                                        categories_cache[category_value] = cat.id
                                    else:
                                        categories_cache[category_value] = None
                                category_id = categories_cache.get(category_value)
                        
                        # Если категория не найдена и есть дефолтная
                        if not category_id and default_category_id:
                            category_id = int(default_category_id)
                        
                        if not category_id:
                            if skip_errors:
                                results["skipped"] += 1
                                continue
                            else:
                                results["errors"].append(f"Строка {row_num}: категория не найдена для '{category_value}'")
                                continue
                        
                        # Остальные поля
                        description = row_lower.get('description', '').strip() or None
                        
                        price_rub = 0
                        price_str = row_lower.get('price rub', '').strip() or row_lower.get('price_rub', '').strip()
                        if price_str:
                            try:
                                price_rub = int(float(price_str))
                            except ValueError:
                                pass
                        
                        photo_url = row_lower.get('photo url', '').strip() or row_lower.get('photo_url', '').strip() or None
                        
                        # Создаем товар
                        product = Product(
                            name=name,
                            category_id=category_id,
                            description=description,
                            price_rub=price_rub,
                            photo_url=photo_url,
                            is_active=True
                        )
                        db.add(product)
                        results["created"] += 1
                        
                    except Exception as e:
                        if skip_errors:
                            results["skipped"] += 1
                        else:
                            results["errors"].append(f"Строка {row_num}: {str(e)}")
                
                # Коммитим если нет ошибок или skip_errors
                if not results["errors"] or skip_errors:
                    db.commit()
                    log_admin_action(
                        request, 
                        "bulk_import", 
                        "Product", 
                        None, 
                        None, 
                        {"created": results["created"], "skipped": results["skipped"]}
                    )
                else:
                    db.rollback()
            
            # Формируем результат
            html_result = f"""
            <div class="container mt-4">
                <h3>Результат импорта</h3>
                <div class="alert alert-success">Создано товаров: {results['created']}</div>
            """
            
            if results["skipped"] > 0:
                html_result += f'<div class="alert alert-warning">Пропущено строк: {results["skipped"]}</div>'
            
            if results["errors"]:
                html_result += f'<div class="alert alert-danger"><h4>Ошибки:</h4><ul>'
                for error in results["errors"][:10]:  # Показываем первые 10 ошибок
                    html_result += f'<li>{error}</li>'
                if len(results["errors"]) > 10:
                    html_result += f'<li>... и еще {len(results["errors"]) - 10} ошибок</li>'
                html_result += '</ul></div>'
            
            html_result += """
                <a href="/admin/product/list" class="btn btn-primary">К списку товаров</a>
            </div>
            """
            
            return HTMLResponse(content=html_result)
        
        # Показываем форму загрузки
        with SessionLocal() as db:
            categories = db.query(Category).filter(Category.is_active == True).order_by(Category.name).all()
            category_options = "\n".join([
                f'<option value="{cat.id}">{cat.name}</option>' 
                for cat in categories
            ])
            
            html = f'''
            <div class="container mt-4">
                <h3>Импорт товаров из CSV</h3>
                <form method="POST" enctype="multipart/form-data">
                    <div class="mb-3">
                        <label class="form-label">CSV файл:</label>
                        <input type="file" class="form-control" name="csv_file" accept=".csv" required>
                        <div class="form-text">
                            Формат CSV с колонками (разделитель - запятая):<br>
                            <code>Name</code> (обязательное) - название товара<br>
                            <code>Category</code> (опционально) - ID или название категории<br>
                            <code>Description</code> (опционально) - описание<br>
                            <code>Price Rub</code> (опционально) - цена в рублях<br>
                            <code>Photo Url</code> (опционально) - URL фото
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Категория по умолчанию (если не указана в CSV):</label>
                        <select class="form-select" name="default_category_id">
                            <option value="">-- Не выбрана --</option>
                            {category_options}
                        </select>
                    </div>
                    <div class="mb-3 form-check">
                        <input type="checkbox" class="form-check-input" name="skip_errors" id="skip_errors" checked>
                        <label class="form-check-label" for="skip_errors">
                            Пропускать ошибочные строки (не прерывать импорт)
                        </label>
                    </div>
                    <div class="alert alert-info">
                        <strong>Пример CSV:</strong><br>
                        <pre>Name,Category,Description,Price Rub,Photo Url
Борщ,Супы,Традиционный украинский суп,350,https://example.com/borsh.jpg
Салат Цезарь,Салаты,Классический салат с курицей,420,</pre>
                    </div>
                    <div class="modal-footer" style="padding-left: 0;">
                        <button type="submit" class="btn btn-primary">Импортировать</button>
                        <a href="/admin/product/list" class="btn btn-secondary">Отмена</a>
                    </div>
                </form>
            </div>
            '''
            return html

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
                    onclick="if(confirm('Отметить заказ #{order.id} как неоплаченный?')){{fetch('/api/admin/orders/update-payment',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{order_id:{order.id},payment_confirmed:false}})}}).then(r=>r.json()).then(d=>{{if(d.success){{this.closest('tr').style.background='#d4edda';setTimeout(()=>location.reload(),300);}}else{{alert('Ошибка: '+d.error);}}}}).catch(e=>alert('Ошибка сети: '+e));}}">
                Оплачено ({method_label})
            </button>
        '''
    else:
        # Красная кнопка - Ожидает оплаты
        html = f'''
            <button type="button" 
                    style="font-size:11px;padding:2px 6px;"
                    class="btn btn-sm btn-danger"
                    onclick="if(confirm('Подтвердить оплату заказа #{order.id}?')){{fetch('/api/admin/orders/update-payment',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{order_id:{order.id},payment_confirmed:true}})}}).then(r=>r.json()).then(d=>{{if(d.success){{this.closest('tr').style.background='#d4edda';setTimeout(()=>location.reload(),300);}}else{{alert('Ошибка: '+d.error);}}}}).catch(e=>alert('Ошибка сети: '+e));}}">
                Ожидает оплаты ({method_label})
            </button>
        '''
    return Markup(html)


def format_product_active_button(product: Product) -> str:
    """Format is_active column with toggle button"""
    
    if product.is_active:
        html = f'''
            <button type="button" 
                    style="font-size:11px;padding:2px 6px;"
                    class="btn btn-sm btn-success"
                    onclick="if(confirm('Деактивировать товар #{product.id}?')){{fetch('/api/admin/products/toggle-active',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{product_id:{product.id},is_active:false}})}}).then(r=>r.json()).then(d=>{{if(d.success){{this.closest('tr').style.background='#d4edda';setTimeout(()=>location.reload(),300);}}else{{alert('Ошибка: '+d.error);}}}}).catch(e=>alert('Ошибка сети: '+e));}}">
                Активен
            </button>
        '''
    else:
        html = f'''
            <button type="button" 
                    style="font-size:11px;padding:2px 6px;"
                    class="btn btn-sm btn-danger"
                    onclick="if(confirm('Активировать товар #{product.id}?')){{fetch('/api/admin/products/toggle-active',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{product_id:{product.id},is_active:true}})}}).then(r=>r.json()).then(d=>{{if(d.success){{this.closest('tr').style.background='#d4edda';setTimeout(()=>location.reload(),300);}}else{{alert('Ошибка: '+d.error);}}}}).catch(e=>alert('Ошибка сети: '+e));}}">
                Неактивен
            </button>
        '''
    
    return Markup(html)


async def toggle_product_active_endpoint(request: Request):
    """AJAX endpoint to toggle product is_active status"""
    try:
        data = await request.json()
        product_id = data.get('product_id')
        is_active = data.get('is_active')
        
        if product_id is None or is_active is None:
            return JSONResponse(
                {"success": False, "error": "Missing product_id or is_active"},
                status_code=400
            )
        
        with SessionLocal() as db:
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                return JSONResponse(
                    {"success": False, "error": "Product not found"},
                    status_code=404
                )
            
            old_status = product.is_active
            product.is_active = bool(is_active)
            db.commit()
            
            log_admin_action(
                request, 
                "toggle_active", 
                "Product", 
                product.id,
                {"is_active": old_status},
                {"is_active": is_active}
            )
            
            return JSONResponse({
                "success": True,
                "product_id": product.id,
                "is_active": product.is_active
            })
            
    except Exception as e:
        logger.error(f"Error toggling product active status: {e}")
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


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
    column_filters = [
        AllUniqueStringValuesFilter(Order.status),
        AllUniqueStringValuesFilter(Order.payment_method),
        AllUniqueStringValuesFilter(Order.delivery_mode),
    ]
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
    column_filters = [
        AllUniqueStringValuesFilter(AdminAuditLog.action),
        AllUniqueStringValuesFilter(AdminAuditLog.entity_type),
        AllUniqueStringValuesFilter(AdminAuditLog.admin_user),
    ]
    name = "Audit Log"
    name_plural = "Audit Logs"
    icon = "fa-solid fa-clipboard-list"
    can_create = False
    can_edit = False
    can_delete = False


class AvailabilityRuleAdmin(ModelView, model=AvailabilityRule):
    """Admin for availability rules (Time-First Menu System)"""
    column_list = [
        AvailabilityRule.id,
        AvailabilityRule.scope_type,
        AvailabilityRule.scope_id,
        AvailabilityRule.daypart,
        AvailabilityRule.lead_time_minutes,
        AvailabilityRule.methods,
        AvailabilityRule.allow_tomorrow,
        AvailabilityRule.is_active,
    ]
    column_sortable_list = [AvailabilityRule.id, AvailabilityRule.lead_time_minutes]
    column_filters = [
        AllUniqueStringValuesFilter(AvailabilityRule.scope_type),
        AllUniqueStringValuesFilter(AvailabilityRule.daypart),
        BooleanFilter(AvailabilityRule.is_active),
    ]
    form_columns = [
        "scope_type",
        "scope_id",
        "daypart",
        "start_time",
        "end_time",
        "lead_time_minutes",
        "methods",
        "allow_tomorrow",
        "tomorrow_cutoff",
        "timezone",
        "is_active",
    ]
    column_labels = {
        AvailabilityRule.scope_type: "Тип",
        AvailabilityRule.scope_id: "ID объекта",
        AvailabilityRule.daypart: "Период",
        AvailabilityRule.lead_time_minutes: "Lead time (мин)",
        AvailabilityRule.methods: "Способы",
        AvailabilityRule.allow_tomorrow: "На завтра",
        AvailabilityRule.is_active: "Активно",
    }
    name = "Правило доступности"
    name_plural = "Правила доступности"
    icon = "fa-solid fa-calendar-check"
    
    async def on_model_change(self, data: dict, model: AvailabilityRule, is_created: bool, request: Request) -> None:
        """Validate availability rule data"""
        # Validate time window consistency
        if data.get("start_time") and data.get("end_time"):
            if data["start_time"] >= data["end_time"]:
                raise ValueError("Время начала должно быть раньше времени окончания")
        
        # Validate lead time for pre-order items
        if data.get("lead_time_minutes", 0) > 0 and data.get("daypart") != "ALLDAY":
            # This is a warning-level validation, not blocking
            logger.info(f"Rule has lead_time {data['lead_time_minutes']} with daypart {data['daypart']}")
        
        # Validate methods array
        methods = data.get("methods", [])
        valid_methods = ["delivery", "pickup"]
        if methods and not all(m in valid_methods for m in methods):
            raise ValueError(f"Methods must be from: {valid_methods}")
        
        action = "create" if is_created else "update"
        log_admin_action(request, action, "AvailabilityRule", model.id, None, data)


class MenuConfigurationAdmin(ModelView, model=MenuConfiguration):
    """Admin for global menu configuration"""
    column_list = [
        MenuConfiguration.id,
        MenuConfiguration.business_tz,
        MenuConfiguration.menu_version,
        MenuConfiguration.enable_tomorrow_orders,
        MenuConfiguration.updated_at,
    ]
    column_sortable_list = [MenuConfiguration.menu_version, MenuConfiguration.updated_at]
    form_columns = [
        "business_tz",
        "morning_start",
        "morning_end",
        "evening_start",
        "evening_end",
        "slot_interval_minutes",
        "base_buffer_minutes",
        "enable_tomorrow_orders",
        "tomorrow_order_cutoff",
        "menu_version",
    ]
    column_labels = {
        MenuConfiguration.business_tz: "Часовой пояс",
        MenuConfiguration.menu_version: "Версия меню",
        MenuConfiguration.enable_tomorrow_orders: "Заказы на завтра",
    }
    name = "Настройки меню"
    name_plural = "Настройки меню"
    icon = "fa-solid fa-cogs"
    can_delete = False  # Prevent deleting the only config record
    
    async def on_model_change(self, data: dict, model: MenuConfiguration, is_created: bool, request: Request) -> None:
        """Validate menu configuration"""
        # Validate time windows
        if data.get("morning_start") and data.get("morning_end"):
            if data["morning_start"] >= data["morning_end"]:
                raise ValueError("Morning start must be before morning end")
        
        if data.get("evening_start") and data.get("evening_end"):
            if data["evening_start"] >= data["evening_end"]:
                raise ValueError("Evening start must be before evening end")
        
        # Ensure only one configuration record exists
        if is_created:
            with SessionLocal() as db:
                existing = db.query(MenuConfiguration).first()
                if existing:
                    raise ValueError("Configuration already exists. Edit the existing record.")
        
        action = "create" if is_created else "update"
        log_admin_action(request, action, "MenuConfiguration", model.id, None, data)


def setup_admin(app, engine):
    admin = Admin(app, engine, title="Sieshka Admin")
    admin.add_view(CategoryAdmin)
    admin.add_view(ProductAdmin)
    admin.add_view(OrderAdmin)
    admin.add_view(OrderItemAdmin)
    admin.add_view(DeliverySlotAdmin)
    admin.add_view(AvailabilityRuleAdmin)
    admin.add_view(MenuConfigurationAdmin)
    admin.add_view(AdminAuditLogAdmin)
    return admin
