const QTY_MIN = 0;
const QTY_MAX = 20;
const MAX_ITEMS = 50;

function cartLoad() {
  try {
    return JSON.parse(localStorage.getItem("cart") || "[]");
  } catch (e) {
    console.error("Error loading cart:", e);
    return [];
  }
}

function cartSave(items) {
  try {
    localStorage.setItem("cart", JSON.stringify(items));
  } catch (e) {
    console.error("Error saving cart:", e);
  }
}

function cartFind(items, productId) {
  return items.findIndex(x => x.product_id === productId);
}

function clampQty(q) {
  if (Number.isNaN(q)) return 0;
  return Math.max(QTY_MIN, Math.min(QTY_MAX, q));
}

function getTotalItems(items) {
  return items.reduce((sum, item) => sum + item.qty, 0);
}

function getTotalPrice(items) {
  return items.reduce((sum, item) => sum + (item.price_rub * item.qty), 0);
}

function sanitizeInput(str) {
  if (!str) return '';
  return str
    .replace(/[<>{}\\/]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function cartSetQty(productId, priceRub, name, qty) {
  qty = clampQty(parseInt(qty, 10));
  name = sanitizeInput(name);
  
  const items = cartLoad();
  const idx = cartFind(items, productId);
  
  const currentQty = idx >= 0 ? items[idx].qty : 0;
  const diff = qty - currentQty;
  const totalItems = getTotalItems(items);
  
  if (diff > 0 && totalItems + diff > MAX_ITEMS) {
    if (typeof CartManager !== 'undefined') {
      CartManager.showToast(`Максимум ${MAX_ITEMS} товаров в корзине`, 'warning');
    }
    return false;
  }

  if (qty <= 0) {
    if (idx >= 0) items.splice(idx, 1);
  } else {
    if (idx >= 0) {
      items[idx].qty = qty;
      items[idx].price_rub = priceRub;
      items[idx].name = name;
    } else {
      items.push({product_id: productId, price_rub: priceRub, name, qty});
    }
  }

  cartSave(items);
  updateQtyInput(productId);
  updateAllQtyInputs();
  updateCartBar();
  updateCartBadge();
  return true;
}

function cartInc(productId, priceRub, name) {
  const items = cartLoad();
  const idx = cartFind(items, productId);
  const cur = idx >= 0 ? items[idx].qty : 0;
  return cartSetQty(productId, priceRub, name, cur + 1);
}

function cartDec(productId, priceRub, name) {
  const items = cartLoad();
  const idx = cartFind(items, productId);
  const cur = idx >= 0 ? items[idx].qty : 0;
  return cartSetQty(productId, priceRub, name, cur - 1);
}

function cartUpdateQty(productId, priceRub, name, delta) {
  const items = cartLoad();
  const idx = cartFind(items, productId);
  const cur = idx >= 0 ? items[idx].qty : 0;
  const newQty = cur + delta;
  
  if (newQty < 0) return false;
  
  const result = cartSetQty(productId, priceRub, name, newQty);
  if (result) {
    renderCart();
  }
  return result;
}

function cartGetItems() {
  return cartLoad().map(x => ({product_id: x.product_id, qty: x.qty}));
}

function cartClear() {
  const items = cartLoad();
  if (items.length === 0) return;
  
  const backupItems = JSON.stringify(items);
  cartSave([]);
  updateAllQtyInputs();
  updateCartBar();
  updateCartBadge();
  renderCart();
  
  window._cartClearBackup = backupItems;
  window._cartClearTimeout = setTimeout(() => {
    delete window._cartClearBackup;
  }, 5000);
}

function cartUndoClear() {
  if (window._cartClearBackup) {
    clearTimeout(window._cartClearTimeout);
    cartSave(JSON.parse(window._cartClearBackup));
    delete window._cartClearBackup;
    updateAllQtyInputs();
    updateCartBar();
    updateCartBadge();
    renderCart();
    return true;
  }
  return false;
}

function getQty(productId) {
  const items = cartLoad();
  const idx = cartFind(items, productId);
  return idx >= 0 ? items[idx].qty : 0;
}

function updateQtyInput(productId) {
  const input = document.getElementById("qty_" + productId);
  if (!input) return;

  const q = getQty(productId);
  input.value = String(q);
}

function updateAllQtyInputs() {
  const inputs = document.querySelectorAll('input[id^="qty_"]');
  inputs.forEach(input => {
    const match = input.id.match(/qty_(\d+)/);
    if (match) {
      const productId = parseInt(match[1]);
      input.value = String(getQty(productId));
    }
  });
}

function updateCartBar() {
  const items = cartLoad();
  const totalItems = getTotalItems(items);
  const totalPrice = getTotalPrice(items);
  
  const summary = document.getElementById('cartSummary');
  if (summary) {
    const itemsText = totalItems === 1 ? 'товар' : totalItems < 5 ? 'товара' : 'товаров';
    summary.textContent = `${totalItems} ${itemsText} · ${totalPrice} ₽`;
  }
}

function updateCartBadge() {
  const items = cartLoad();
  const totalItems = getTotalItems(items);
  const badge = document.getElementById('cartBadge');
  
  if (badge) {
    if (totalItems > 0) {
      badge.textContent = totalItems > 99 ? '99+' : totalItems;
      badge.classList.remove('d-none');
    } else {
      badge.classList.add('d-none');
    }
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function escapeJsString(str) {
  return str
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r');
}

function renderCart() {
  const items = cartLoad();
  const container = document.getElementById('cart');
  const emptyCart = document.getElementById('emptyCart');
  const cartReal = document.getElementById('cartReal');
  const cartActions = document.getElementById('cartActions');
  
  if (!container) return;
  
  if (items.length === 0) {
    container.innerHTML = '';
    if (emptyCart) emptyCart.classList.remove('d-none');
    if (cartReal) cartReal.classList.add('d-none');
    if (cartActions) cartActions.classList.add('d-none');
    return;
  }
  
  if (emptyCart) emptyCart.classList.add('d-none');
  if (cartReal) cartReal.classList.remove('d-none');
  if (cartActions) cartActions.classList.remove('d-none');
  
  let html = '<div class="vstack gap-2">';
  let total = 0;
  
  items.forEach(item => {
    const itemTotal = item.price_rub * item.qty;
    total += itemTotal;
    
    html += `
      <div class="d-flex justify-content-between align-items-center">
        <div style="flex: 1; min-width: 0;">
          <div class="fw-semibold text-truncate">${escapeHtml(item.name)}</div>
          <div class="text-muted small">${item.price_rub} ₽/шт</div>
        </div>
        <div class="d-flex align-items-center gap-2" style="flex-shrink: 0;">
          <button type="button" class="btn btn-sm btn-outline-secondary" style="width: 28px; height: 28px; padding: 0; line-height: 1;" 
                  onclick="cartUpdateQty(${item.product_id}, ${item.price_rub}, '${escapeJsString(item.name)}', -1)">−</button>
          <span class="fw-semibold" style="min-width: 24px; text-align: center;">${item.qty}</span>
          <button type="button" class="btn btn-sm btn-outline-secondary" style="width: 28px; height: 28px; padding: 0; line-height: 1;" 
                  onclick="cartUpdateQty(${item.product_id}, ${item.price_rub}, '${escapeJsString(item.name)}', 1)">+</button>
        </div>
        <div class="fw-bold ms-3" style="min-width: 70px; text-align: right;">${itemTotal} ₽</div>
      </div>
    `;
  });
  
  html += '</div>';
  html += `
    <hr>
    <div class="d-flex justify-content-between fw-bold h5 mb-0">
      <span>Итого:</span>
      <span>${total} ₽</span>
    </div>
  `;
  
  container.innerHTML = html;
}

function generateIdempotencyKey() {
  return 'id_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

function initCartPage() {
  if (window._cartPageInitialized) return;
  window._cartPageInitialized = true;
  
  renderCart();
  updateCartBar();
  updateCartBadge();
}

function initCheckoutPage() {
  renderCart();
  updateCheckoutTotal();
  setupCheckoutForm();
}

function updateCheckoutTotal() {
  const items = cartLoad();
  const total = getTotalPrice(items);
  const totalEl = document.getElementById('checkoutTotal');
  if (totalEl) {
    totalEl.textContent = total + ' ₽';
  }
}

function setupCheckoutForm() {
  const form = document.getElementById('orderForm');
  if (!form) return;
  
  form.addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const items = cartLoad();
    if (items.length === 0) {
      showError('Корзина пуста');
      return;
    }
    
    const submitBtn = document.getElementById('submitBtn');
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Оформляем...';
    
    const deliveryMode = document.querySelector('input[name="delivery_mode"]:checked').value;
    
    const formData = {
      name: sanitizeInput(document.getElementById('name').value),
      phone: sanitizeInput(document.getElementById('phone').value),
      address: sanitizeInput(document.getElementById('address').value),
      comment: sanitizeInput(document.getElementById('comment').value) || null,
      delivery_mode: deliveryMode,
      delivery_slot: null,
      delivery_date: null,
      payment_method: document.querySelector('input[name="payment_method"]:checked').value,
      items: items.map(item => ({
        product_id: item.product_id,
        qty: item.qty
      })),
      idempotency_key: generateIdempotencyKey()
    };
    
    // Add slot data if slot delivery selected
    if (deliveryMode === 'slot') {
      formData.delivery_slot = document.getElementById('delivery_slot').value;
      formData.delivery_date = document.getElementById('delivery_date').value;
      
      if (!formData.delivery_slot) {
        showError('Выберите время доставки');
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
        return;
      }
      
      if (!formData.delivery_date) {
        showError('Выберите дату доставки');
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
        return;
      }
    }
    
    try {
      const response = await fetch('/api/orders', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify(formData)
      });
      
      const data = await response.json();
      
      if (response.ok && data.ok) {
        window.location.href = '/thanks/' + data.order_id;
      } else {
        showError(data.detail || 'Ошибка при оформлении заказа');
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
      }
    } catch (error) {
      console.error('Error:', error);
      showError('Ошибка соединения. Попробуйте позже.');
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  });
}

function showError(message) {
  const errorDiv = document.getElementById('formError');
  if (errorDiv) {
    errorDiv.textContent = message;
    errorDiv.classList.remove('d-none');
  }
}

document.addEventListener('DOMContentLoaded', function() {
  updateCartBar();
  updateCartBadge();
});
