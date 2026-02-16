/**
 * Unified Cart System for Sieshka Food Delivery
 * Compatible with: menu.html, cart.html, checkout.html
 * Storage format: [{product_id, price_rub, name, qty}, ...]
 */

const CartManager = (function() {
  'use strict';
  
  // Constants
  const STORAGE_KEY = 'cart';
  const QTY_MIN = 0;
  const QTY_MAX = 20;
  const MAX_ITEMS = 50;
  
  // State
  let offcanvasInstance = null;
  let toastTimeout = null;
  
  // Utility functions
  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
  
  function escapeJs(str) {
    if (!str) return '';
    return String(str)
      .replace(/\\/g, '\\\\')
      .replace(/'/g, "\\'")
      .replace(/"/g, '\\"')
      .replace(/\n/g, '\\n')
      .replace(/\r/g, '\\r');
  }
  
  function formatPrice(price) {
    return Math.round(price).toLocaleString('ru-RU') + ' ₽';
  }
  
  function getItemWord(count) {
    if (count % 10 === 1 && count % 100 !== 11) return 'товар';
    if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) return 'товара';
    return 'товаров';
  }
  
  // Cart Storage Operations
  function loadCart() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      const cart = stored ? JSON.parse(stored) : [];
      return Array.isArray(cart) ? cart : [];
    } catch (e) {
      console.error('Error loading cart:', e);
      return [];
    }
  }
  
  function saveCart(items) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch (e) {
      console.error('Error saving cart:', e);
    }
  }
  
  function findItemIndex(items, productId) {
    return items.findIndex(item => item.product_id === productId);
  }
  
  function getTotalItems(items) {
    return items.reduce((sum, item) => sum + item.qty, 0);
  }
  
  function getTotalPrice(items) {
    return items.reduce((sum, item) => sum + (item.price_rub * item.qty), 0);
  }
  
  // Cart Operations
  function addItem(productId, priceRub, name) {
    const items = loadCart();
    const idx = findItemIndex(items, productId);
    
    if (idx >= 0) {
      // Item exists, increment
      const newQty = items[idx].qty + 1;
      if (newQty > QTY_MAX) {
        showToast('Достигнут лимит: макс. 20 шт. на товар', 'warning');
        return false;
      }
      items[idx].qty = newQty;
    } else {
      // New item
      const totalItems = getTotalItems(items);
      if (totalItems >= MAX_ITEMS) {
        showToast(`Максимум ${MAX_ITEMS} товаров в корзине`, 'warning');
        return false;
      }
      items.push({
        product_id: productId,
        price_rub: priceRub,
        name: name,
        qty: 1
      });
    }
    
    saveCart(items);
    updateAllUI();
    showToast(`Добавлено: ${name}`, 'success', true);
    return true;
  }
  
  function updateQty(productId, delta) {
    const items = loadCart();
    const idx = findItemIndex(items, productId);
    
    if (idx < 0 && delta > 0) {
      // Trying to add new item via delta - not supported without price/name
      console.warn('Cannot add new item via updateQty - use addItem');
      return false;
    }
    
    if (idx >= 0) {
      const newQty = items[idx].qty + delta;
      
      if (newQty <= 0) {
        // Remove item
        items.splice(idx, 1);
      } else if (newQty > QTY_MAX) {
        showToast('Достигнут лимит: макс. 20 шт. на товар', 'warning');
        return false;
      } else {
        items[idx].qty = newQty;
        
        // Check total items limit
        const totalItems = getTotalItems(items);
        if (totalItems > MAX_ITEMS) {
          showToast(`Максимум ${MAX_ITEMS} товаров в корзине`, 'warning');
          return false;
        }
      }
      
      saveCart(items);
      updateAllUI();
      
      // Show toast for quantity change
      if (delta > 0) {
        showToast('Количество увеличено', 'success');
      } else if (newQty > 0) {
        showToast('Количество уменьшено', 'info');
      } else {
        showToast('Товар удален из корзины', 'info');
      }
      
      return true;
    }
    
    return false;
  }
  
  function setQty(productId, priceRub, name, qty) {
    qty = Math.max(QTY_MIN, Math.min(QTY_MAX, parseInt(qty) || 0));
    
    const items = loadCart();
    const idx = findItemIndex(items, productId);
    
    if (qty <= 0) {
      if (idx >= 0) {
        items.splice(idx, 1);
      }
    } else {
      if (idx >= 0) {
        items[idx].qty = qty;
      } else {
        items.push({
          product_id: productId,
          price_rub: priceRub,
          name: name,
          qty: qty
        });
      }
    }
    
    // Validate total items
    const totalItems = getTotalItems(items);
    if (totalItems > MAX_ITEMS) {
      showToast(`Максимум ${MAX_ITEMS} товаров в корзине`, 'warning');
      return false;
    }
    
    saveCart(items);
    updateAllUI();
    return true;
  }
  
  function removeItem(productId) {
    const items = loadCart();
    const idx = findItemIndex(items, productId);
    
    if (idx >= 0) {
      items.splice(idx, 1);
      saveCart(items);
      updateAllUI();
      showToast('Товар удален из корзины', 'info');
      return true;
    }
    
    return false;
  }
  
  function clearCart() {
    if (confirm('Очистить корзину?')) {
      saveCart([]);
      updateAllUI();
      showToast('Корзина очищена', 'info');
      return true;
    }
    return false;
  }
  
  function getItemQty(productId) {
    const items = loadCart();
    const idx = findItemIndex(items, productId);
    return idx >= 0 ? items[idx].qty : 0;
  }
  
  function getItems() {
    return loadCart().map(item => ({
      product_id: item.product_id,
      qty: item.qty
    }));
  }
  
  // UI Update Functions
  function updateNavbarCart() {
    const items = loadCart();
    const totalItems = getTotalItems(items);
    const totalPrice = getTotalPrice(items);
    
    // Update navbar cart summary
    const summaryEl = document.getElementById('navbarCartSummary');
    if (summaryEl) {
      if (totalItems > 0) {
        summaryEl.textContent = `${totalItems} · ${formatPrice(totalPrice)}`;
      } else {
        summaryEl.textContent = '';
      }
    }
    
    // Update navbar cart badge
    const badgeEl = document.getElementById('navbarCartBadge');
    if (badgeEl) {
      if (totalItems > 0) {
        badgeEl.textContent = totalItems > 99 ? '99+' : totalItems;
        badgeEl.classList.remove('d-none');
      } else {
        badgeEl.classList.add('d-none');
      }
    }
    
    // Legacy support: cartBadge (old ID)
    const legacyBadge = document.getElementById('cartBadge');
    if (legacyBadge) {
      if (totalItems > 0) {
        legacyBadge.textContent = totalItems > 99 ? '99+' : totalItems;
        legacyBadge.classList.remove('d-none');
      } else {
        legacyBadge.classList.add('d-none');
      }
    }
    
    // Legacy support: cart-total and cart-badge from menu.html
    const menuCartTotal = document.getElementById('cart-total');
    if (menuCartTotal) {
      menuCartTotal.textContent = formatPrice(totalPrice);
    }
    
    const menuCartBadge = document.getElementById('cart-badge');
    if (menuCartBadge) {
      menuCartBadge.textContent = totalItems;
      menuCartBadge.style.display = totalItems > 0 ? 'inline' : 'none';
    }
  }
  
  function updateOffcanvasCart() {
    const items = loadCart();
    const container = document.getElementById('offcanvasCartItems');
    const emptyMessage = document.getElementById('offcanvasEmptyMessage');
    const footer = document.getElementById('offcanvasCartFooter');
    const totalEl = document.getElementById('offcanvasCartTotal');
    
    if (!container) return;
    
    if (items.length === 0) {
      container.classList.add('d-none');
      container.innerHTML = '';
      if (emptyMessage) emptyMessage.classList.remove('d-none');
      if (footer) footer.classList.add('d-none');
      return;
    }
    
    container.classList.remove('d-none');
    if (emptyMessage) emptyMessage.classList.add('d-none');
    if (footer) footer.classList.remove('d-none');
    
    let html = '';
    let total = 0;
    
    items.forEach(item => {
      const itemTotal = item.price_rub * item.qty;
      total += itemTotal;
      
      html += `
        <div class="cart-item" data-product-id="${item.product_id}">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <div style="flex: 1; min-width: 0;">
              <div class="cart-item-name text-truncate">${escapeHtml(item.name)}</div>
              <div class="cart-item-price">${formatPrice(item.price_rub)}/шт</div>
            </div>
            <div class="cart-item-total ms-2">${formatPrice(itemTotal)}</div>
          </div>
          <div class="d-flex justify-content-between align-items-center">
            <div class="qty-control">
              <button type="button" class="qty-btn" 
                      onclick="CartManager.updateQty(${item.product_id}, -1)"
                      ${item.qty <= 1 ? '' : ''}>
                −
              </button>
              <span class="qty-value">${item.qty}</span>
              <button type="button" class="qty-btn" 
                      onclick="CartManager.updateQty(${item.product_id}, 1)"
                      ${item.qty >= QTY_MAX ? 'disabled' : ''}>
                +
              </button>
            </div>
            <button type="button" class="btn btn-sm btn-link text-danger p-0" 
                    onclick="CartManager.removeItem(${item.product_id})"
                    style="font-size: 0.8rem;">
              Удалить
            </button>
          </div>
        </div>
      `;
    });
    
    container.innerHTML = html;
    
    if (totalEl) {
      totalEl.textContent = formatPrice(total);
    }
  }
  
  function updateProductControls() {
    // Update quantity controls on product cards
    const controls = document.querySelectorAll('[data-product-id]');
    controls.forEach(el => {
      const productId = parseInt(el.dataset.productId);
      if (!productId) return;
      
      const qty = getItemQty(productId);
      const qtyDisplay = el.querySelector('.qty-display');
      const qtyInput = el.querySelector('.qty-input');
      
      if (qtyDisplay) {
        qtyDisplay.textContent = qty;
      }
      if (qtyInput) {
        qtyInput.value = qty;
      }
      
      // Toggle between "Add" button and quantity controls
      const addBtn = el.querySelector('.btn-add-to-cart');
      const qtyControl = el.querySelector('.qty-control-group');
      
      if (addBtn && qtyControl) {
        if (qty > 0) {
          addBtn.classList.add('d-none');
          qtyControl.classList.remove('d-none');
        } else {
          addBtn.classList.remove('d-none');
          qtyControl.classList.add('d-none');
        }
      }
    });
  }
  
  function renderCartPage() {
    // Render cart for cart.html
    const container = document.getElementById('cart');
    const emptyCart = document.getElementById('emptyCart');
    const cartReal = document.getElementById('cartReal');
    const cartActions = document.getElementById('cartActions');
    
    if (!container) return;
    
    const items = loadCart();
    
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
    
    let html = '<div class="vstack gap-3">';
    let total = 0;
    
    items.forEach(item => {
      const itemTotal = item.price_rub * item.qty;
      total += itemTotal;
      
      html += `
        <div class="d-flex justify-content-between align-items-center py-2 border-bottom">
          <div style="flex: 1; min-width: 0;">
            <div class="fw-semibold text-truncate">${escapeHtml(item.name)}</div>
            <div class="text-muted small">${formatPrice(item.price_rub)}/шт</div>
          </div>
          <div class="d-flex align-items-center gap-2" style="flex-shrink: 0;">
            <button type="button" class="btn btn-sm btn-outline-secondary rounded-circle" style="width: 32px; height: 32px; padding: 0;"
                    onclick="CartManager.updateQty(${item.product_id}, -1)">−</button>
            <span class="fw-semibold" style="min-width: 28px; text-align: center;">${item.qty}</span>
            <button type="button" class="btn btn-sm btn-outline-secondary rounded-circle" style="width: 32px; height: 32px; padding: 0;"
                    onclick="CartManager.updateQty(${item.product_id}, 1)"
                    ${item.qty >= QTY_MAX ? 'disabled' : ''}>+</button>
          </div>
          <div class="fw-bold ms-3" style="min-width: 80px; text-align: right;">${formatPrice(itemTotal)}</div>
        </div>
      `;
    });
    
    html += '</div>';
    html += `
      <div class="d-flex justify-content-between fw-bold h5 mb-0 mt-3 pt-3 border-top">
        <span>Итого:</span>
        <span>${formatPrice(total)}</span>
      </div>
    `;
    
    container.innerHTML = html;
  }
  
  function updateCheckoutTotal() {
    const totalEl = document.getElementById('checkoutTotal');
    if (totalEl) {
      const items = loadCart();
      const total = getTotalPrice(items);
      totalEl.textContent = formatPrice(total);
    }
  }
  
  function updateAllUI() {
    updateNavbarCart();
    updateOffcanvasCart();
    updateProductControls();
    renderCartPage();
    updateCheckoutTotal();
  }
  
  // Toast Notifications
  function showToast(message, type = 'info', showCartSummary = false) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    // Clear existing timeout
    if (toastTimeout) {
      clearTimeout(toastTimeout);
    }
    
    // Remove existing toasts
    container.innerHTML = '';
    
    const items = loadCart();
    const totalItems = getTotalItems(items);
    const totalPrice = getTotalPrice(items);
    
    const toastId = 'cartToast' + Date.now();
    
    let icon = 'info-circle';
    let bgClass = 'bg-primary';
    
    switch(type) {
      case 'success':
        icon = 'check-circle';
        break;
      case 'warning':
        icon = 'exclamation-triangle';
        break;
      case 'error':
        icon = 'x-circle';
        break;
    }
    
    const cartSummaryHtml = showCartSummary && totalItems > 0 ? `
      <div class="toast-footer">
        <span class="toast-cart-summary">
          ${totalItems} ${getItemWord(totalItems)} · ${formatPrice(totalPrice)}
        </span>
        <button type="button" class="btn btn-sm btn-brand" data-bs-toggle="offcanvas" data-bs-target="#offcanvasCart">
          Открыть корзину
        </button>
      </div>
    ` : '';
    
    const toastHtml = `
      <div class="toast show" id="${toastId}" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="toast-header">
          <i class="bi bi-${icon} me-2"></i>
          <strong class="me-auto">Корзина обновлена</strong>
          <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
        <div class="toast-body">
          ${escapeHtml(message)}
        </div>
        ${cartSummaryHtml}
      </div>
    `;
    
    container.innerHTML = toastHtml;
    
    // Auto-hide after 4 seconds
    toastTimeout = setTimeout(() => {
      const toast = document.getElementById(toastId);
      if (toast) {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
      }
    }, 4000);
  }
  
  // Event Handlers
  function setupEventListeners() {
    // Offcanvas clear button
    const clearBtn = document.getElementById('offcanvasClearBtn');
    if (clearBtn) {
      clearBtn.addEventListener('click', function() {
        clearCart();
      });
    }
    
    // Setup offcanvas instance
    const offcanvasEl = document.getElementById('offcanvasCart');
    if (offcanvasEl && typeof bootstrap !== 'undefined') {
      offcanvasInstance = new bootstrap.Offcanvas(offcanvasEl);
    }
  }
  
  // Public API
  return {
    // Initialization
    init: function() {
      setupEventListeners();
      updateAllUI();
    },
    
    // Cart operations
    addItem: addItem,
    updateQty: updateQty,
    setQty: setQty,
    removeItem: removeItem,
    clearCart: clearCart,
    getItemQty: getItemQty,
    getItems: getItems,
    loadCart: loadCart,
    
    // UI updates
    updateAllUI: updateAllUI,
    renderCartPage: renderCartPage,
    updateCheckoutTotal: updateCheckoutTotal,
    showToast: showToast,
    
    // Constants
    QTY_MAX: QTY_MAX,
    MAX_ITEMS: MAX_ITEMS
  };
})();

// Legacy function support for backward compatibility
function cartLoad() {
  return CartManager.loadCart();
}

function cartSave(items) {
  localStorage.setItem('cart', JSON.stringify(items));
}

function cartFind(items, productId) {
  return items.findIndex(x => x.product_id === productId);
}

function getTotalItems(items) {
  return items.reduce((sum, item) => sum + item.qty, 0);
}

function getTotalPrice(items) {
  return items.reduce((sum, item) => sum + (item.price_rub * item.qty), 0);
}

function cartSetQty(productId, priceRub, name, qty) {
  return CartManager.setQty(productId, priceRub, name, qty);
}

function cartInc(productId, priceRub, name) {
  return CartManager.addItem(productId, priceRub, name);
}

function cartDec(productId, priceRub, name) {
  return CartManager.updateQty(productId, -1);
}

function cartUpdateQty(productId, priceRub, name, delta) {
  return CartManager.updateQty(productId, delta);
}

function cartGetItems() {
  return CartManager.getItems();
}

function cartClear() {
  return CartManager.clearCart();
}

function getQty(productId) {
  return CartManager.getItemQty(productId);
}

function updateQtyInput(productId) {
  // Legacy support - now handled by updateProductControls
  CartManager.updateAllUI();
}

function updateAllQtyInputs() {
  // Legacy support
  CartManager.updateProductControls();
}

function updateCartBar() {
  // Legacy support
  CartManager.updateNavbarCart();
}

function updateCartBadge() {
  // Legacy support
  CartManager.updateNavbarCart();
}

function renderCart() {
  // Legacy support
  CartManager.renderCartPage();
}

function initCartPage() {
  CartManager.renderCartPage();
  CartManager.updateNavbarCart();
}

function initCheckoutPage() {
  CartManager.renderCartPage();
  CartManager.updateCheckoutTotal();
  setupCheckoutForm();
}

function setupCheckoutForm() {
  const form = document.getElementById('orderForm');
  if (!form) return;
  
  form.addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const items = CartManager.loadCart();
    if (items.length === 0) {
      showError('Корзина пуста');
      return;
    }
    
    const submitBtn = document.getElementById('submitBtn');
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Оформляем...';
    
    const deliveryMode = document.querySelector('input[name="delivery_mode"]:checked').value;
    
    const sanitizeInput = (str) => {
      if (!str) return '';
      return String(str)
        .replace(/[<>{}\\/]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
    };
    
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
      idempotency_key: 'id_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
    };
    
    if (deliveryMode === 'slot') {
      formData.delivery_slot = document.getElementById('delivery_slot').value;
      formData.delivery_date = document.getElementById('delivery_date').value;
      
      if (!formData.delivery_slot) {
        showError('Выберите время доставки');
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
        return;
      }
      
      if (!formData.delivery_date) {
        showError('Выберите дату доставки');
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
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
        // Clear cart on successful order
        localStorage.setItem('cart', '[]');
        window.location.href = '/thanks/' + data.order_id;
      } else {
        showError(data.detail || 'Ошибка при оформлении заказа');
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
      }
    } catch (error) {
      console.error('Error:', error);
      showError('Ошибка соединения. Попробуйте позже.');
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalText;
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

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
  CartManager.init();
});
