#!/usr/bin/env python3
"""
Применяет патч ЮKassa-виджет к main.py и cart.js.
Запускать из корня репозитория: python3 patch.py
"""
import re, sys

# ── main.py ───────────────────────────────────────────────────────────────────
MAIN = 'app/main.py'
with open(MAIN, encoding='utf-8') as f:
    src = f.read()

orig = src

# 1. переменная
src = src.replace(
    'confirmation_url: str | None = None',
    'confirmation_token: str | None = None',
    1,
)
# 2. вызов
src = src.replace(
    'confirmation_url = create_yookassa_payment(order, db)',
    'confirmation_token = create_yookassa_payment(order, db)',
    1,
)
# 3. ответ API
src = src.replace(
    '"confirmation_url": confirmation_url,',
    '"confirmation_token": confirmation_token,',
    1,
)
# 4. CSP — добавляем домены ЮKassa
OLD_CSP = (
    "\"default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https:; "
    "font-src 'self' https://cdn.jsdelivr.net https://r2cdn.perplexity.ai; "
    "connect-src 'self' https://cdn.jsdelivr.net;\""
)
NEW_CSP = (
    "\"default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://yookassa.ru https://static.yoomoney.ru; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https:; "
    "font-src 'self' https://cdn.jsdelivr.net https://r2cdn.perplexity.ai; "
    "connect-src 'self' https://cdn.jsdelivr.net https://yookassa.ru https://api.yookassa.ru; "
    "frame-src https://yookassa.ru https://static.yoomoney.ru;\""
)
src = src.replace(OLD_CSP, NEW_CSP, 1)

if src == orig:
    print("main.py: ни одна замена не сработала — проверь вручную", file=sys.stderr)
    sys.exit(1)

with open(MAIN, 'w', encoding='utf-8') as f:
    f.write(src)
print("main.py ✓")

# ── cart.js ───────────────────────────────────────────────────────────────────
CART = 'app/static/js/cart.js'
with open(CART, encoding='utf-8') as f:
    js = f.read()

orig_js = js

NEW_FUNCTIONS = r"""
function showYooKassaWidget(confirmationToken, orderId) {
    const form = document.getElementById('orderForm');
    let widgetContainer = document.getElementById('yookassa-payment-form');
    if (!widgetContainer) {
        widgetContainer = document.createElement('div');
        widgetContainer.id = 'yookassa-payment-form';
        widgetContainer.style.minHeight = '200px';
        if (form) form.parentNode.insertBefore(widgetContainer, form.nextSibling);
        else document.body.appendChild(widgetContainer);
    }
    if (form) form.classList.add('d-none');
    if (!window.YooMoneyCheckoutWidget) {
        const script = document.createElement('script');
        script.src = 'https://yookassa.ru/integration/simplepay/widget';
        script.onload = () => initYooKassaWidget(confirmationToken, orderId, widgetContainer);
        script.onerror = () => {
            CartManager.showToast('Не удалось загрузить платёжный виджет', 'error');
            if (form) form.classList.remove('d-none');
        };
        document.head.appendChild(script);
    } else {
        initYooKassaWidget(confirmationToken, orderId, widgetContainer);
    }
}

function initYooKassaWidget(confirmationToken, orderId, container) {
    const checkout = new window.YooMoneyCheckoutWidget({
        confirmation_token: confirmationToken,
        return_url: window.location.origin + '/thanks/' + orderId,
        customization: { payment_methods: ['bank_card', 'sbp'] },
        error_callback: function(error) {
            console.error('YooKassa widget error:', error);
            CartManager.showToast('Ошибка платёжного виджета', 'error');
        }
    });
    checkout.render(container.id);
}

"""

js = js.replace('function setupCheckoutForm(', NEW_FUNCTIONS + 'function setupCheckoutForm(', 1)

# Меняем обработчик ответа: confirmation_url → confirmation_token + виджет
js = re.sub(
    r"if\s*\(data\.confirmation_url\)\s*\{[^}]*\}\s*else\s*\{",
    "if (data.confirmation_token) {\n"
    "                    showYooKassaWidget(data.confirmation_token, data.order_id);\n"
    "                } else {",
    js,
    count=1,
)

if js == orig_js:
    print("cart.js: ни одна замена не сработала — проверь вручную", file=sys.stderr)
    sys.exit(1)

with open(CART, 'w', encoding='utf-8') as f:
    f.write(js)
print("cart.js ✓")

print("\nПатч применён. Перезапусти контейнер: docker compose restart api_green")
