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
  const HISTORY_KEY = 'cart_history';
  let recentlyDeleted = loadHistory(); // Load last 3 deleted items from localStorage
  const upsellSuggestions = []; // Populated from menu.js
  let deliveryFee = 0; // Delivery fee from server configuration
  let deliveryFeeLoaded = false; // Flag to track if delivery fee was loaded
  
  function loadHistory() {
    try {
      const stored = localStorage.getItem(HISTORY_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch (e) {
      return [];
    }
  }

  function saveHistory() {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(recentlyDeleted.slice(0, 3)));
    } catch (e) {
      console.error('Error saving history:', e);
    }
  }

  // Load delivery fee from server
  async function loadDeliveryFee() {
    if (deliveryFeeLoaded) return deliveryFee;
    
    try {
      const response = await fetch('/api/config/delivery-fee');
      if (response.ok) {
        const data = await response.json();
        deliveryFee = data.delivery_fee || 0;
        deliveryFeeLoaded = true;
      }
    } catch (e) {
      console.error('Error loading delivery fee:', e);
      deliveryFee = 0;
    }
    return deliveryFee;
  }

  // Get delivery fee (loads from server if not already loaded)
  async function getDeliveryFee() {
    if (!deliveryFeeLoaded) {
      await loadDeliveryFee();
    }
    return deliveryFee;
  }
  
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
  function trackDeleted(item) {
    const existing = recentlyDeleted.findIndex(x => x.product_id === item.product_id);
    if (existing >= 0) recentlyDeleted.splice(existing, 1);
    recentlyDeleted.unshift({
        product_id: item.product_id,
        name: item.name,
        price_rub: item.price_rub
    });
    if (recentlyDeleted.length > 3) recentlyDeleted.pop();
    saveHistory();
  }

  function addItem(productId, priceRub, name) {
    const items = loadCart();
    const idx = findItemIndex(items, productId);
    const totalItems = getTotalItems(items);
    
    if (idx >= 0) {
      // Item exists, increment
      const newQty = items[idx].qty + 1;
      if (newQty > QTY_MAX) {
        showToast('Достигнут лимит: макс. 20 шт. на товар', 'warning');
        return false;
      }
      items[idx].qty = newQty;
    } else {
      // New item - check limit only for new items
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
      // Remove from recently deleted if it was there
      const rdIdx = recentlyDeleted.findIndex(x => x.product_id === productId);
      if (rdIdx >= 0) recentlyDeleted.splice(rdIdx, 1);
    }
    
    saveCart(items);
    updateAllUI();
    return true;
  }
  
  function updateQty(productId, delta) {
    const items = loadCart();
    const idx = findItemIndex(items, productId);
    
    if (idx < 0 && delta > 0) {
      console.warn('Cannot add new item via updateQty - use addItem');
      return false;
    }
    
    if (idx >= 0) {
      const newQty = items[idx].qty + delta;
      
      if (newQty <= 0) {
        trackDeleted(items[idx]);
        items.splice(idx, 1);
      } else if (newQty > QTY_MAX) {
        showToast('Достигнут лимит: макс. 20 шт. на товар', 'warning');
        return false;
      } else {
        const totalItems = getTotalItems(items);
        if (delta > 0 && totalItems >= MAX_ITEMS) {
          showToast(`Максимум ${MAX_ITEMS} товаров в корзине`, 'warning');
          return false;
        }
        items[idx].qty = newQty;
      }
      
      saveCart(items);
      updateAllUI();
      
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
      trackDeleted(items[idx]);
      items.splice(idx, 1);
      saveCart(items);
      updateAllUI();
      return true;
    }
    
    return false;
  }
  
  let _clearBackup = null;
  let _clearBackupTimeout = null;
  
  function clearCart() {
    const items = loadCart();
    if (items.length === 0) return true;
    
    _clearBackup = JSON.stringify(items);
    if (_clearBackupTimeout) clearTimeout(_clearBackupTimeout);
    _clearBackupTimeout = setTimeout(() => {
      _clearBackup = null;
    }, 5000);
    
    saveCart([]);
    updateAllUI();
    showUndoToast('Корзина очищена', undoClearCart);
    return true;
  }
  
  function undoClearCart() {
    if (!_clearBackup) return false;
    
    clearTimeout(_clearBackupTimeout);
    saveCart(JSON.parse(_clearBackup));
    _clearBackup = null;
    updateAllUI();
    return true;
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
  async function updateNavbarCart() {
    const items = loadCart();
    const totalItems = getTotalItems(items);
    const subtotal = getTotalPrice(items);
    const currentDeliveryFee = totalItems > 0 && deliveryFeeLoaded ? deliveryFee : 0;
    const totalPrice = subtotal + currentDeliveryFee;
    
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
  
  async function updateOffcanvasCart() {
    const items = loadCart();
    const container = document.getElementById('offcanvasCartItems');
    const emptyMessage = document.getElementById('offcanvasEmptyMessage');
    const footer = document.getElementById('offcanvasCartFooter');
    const subtotalEl = document.getElementById('offcanvasCartSubtotal');
    const deliveryEl = document.getElementById('offcanvasCartDeliveryFee');
    const totalEl = document.getElementById('offcanvasCartTotal');
    
    if (!container) return;
    
    if (items.length === 0 && recentlyDeleted.length === 0) {
      container.classList.add('d-none');
      container.innerHTML = '';
      if (emptyMessage) emptyMessage.classList.remove('d-none');
      if (footer) footer.classList.add('d-none');
      return;
    }
    
    container.classList.remove('d-none');
    if (emptyMessage) emptyMessage.classList.add('d-none');
    if (footer) footer.classList.remove('d-none');
    
    let html = '<div class="cart-items-list">';
    let subtotal = 0;
    
    items.forEach(item => {
      const itemTotal = item.price_rub * item.qty;
      subtotal += itemTotal;
      
      html += `
        <div class="cart-item" data-product-id="${item.product_id}" data-name="${escapeHtml(item.name)}" data-price="${item.price_rub}">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <div style="flex: 1; min-width: 0;">
              <div class="cart-item-name text-truncate fw-bold">${escapeHtml(item.name)}</div>
              <div class="cart-item-price small text-muted">${formatPrice(item.price_rub)}/шт</div>
            </div>
            <div class="cart-item-total fw-bold text-brand">${formatPrice(itemTotal)}</div>
          </div>
          <div class="d-flex justify-content-between align-items-center">
            <div class="qty-control">
              <button type="button" class="qty-btn" data-action="dec">
                −
              </button>
              <span class="qty-value">${item.qty}</span>
              <button type="button" class="qty-btn" data-action="inc" ${item.qty >= QTY_MAX ? 'disabled' : ''}>
                +
              </button>
            </div>
            <button type="button" class="btn btn-sm text-danger p-0" data-action="remove" style="font-size: 0.8rem;">
              <i class="bi bi-trash me-1"></i>Удалить
            </button>
          </div>
        </div>
      `;
    });
    html += '</div>';

    // Add Upsell suggestions if available and not already in cart
    const filteredUpsell = upsellSuggestions.filter(u => !items.some(i => i.product_id === u.product_id)).slice(0, 3);
    if (filteredUpsell.length > 0) {
      html += `
        <div class="upsell-section mt-4 bg-light p-3 rounded-4 mx-2">
          <div class="small text-muted text-uppercase fw-bold mb-2" style="font-size: 0.7rem;">Не забудьте добавить:</div>
          <div class="d-flex flex-column gap-2">
            ${filteredUpsell.map(u => `
              <div class="d-flex justify-content-between align-items-center" data-product-id="${u.product_id}" data-name="${escapeHtml(u.name)}" data-price="${u.price_rub}">
                <div style="flex: 1; min-width: 0;">
                  <div class="small text-truncate fw-semibold">${escapeHtml(u.name)}</div>
                  <div class="small text-brand">${formatPrice(u.price_rub)}</div>
                </div>
                <button type="button" class="btn btn-sm btn-brand rounded-pill px-3" data-action="add" style="font-size: 0.75rem;">
                  +
                </button>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    // Add "Add for Later" section - items available later/tomorrow
    const laterItems = getAddForLaterItems ? getAddForLaterItems().filter(u => !items.some(i => i.product_id === u.product_id)) : [];
    if (laterItems.length > 0) {
      html += `
        <div class="add-for-later-section mt-4 p-3 rounded-4 mx-2" style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border: 1px dashed var(--color-accent-border);">
          <div class="small text-muted text-uppercase fw-bold mb-2" style="font-size: 0.7rem;">
            <i class="bi bi-clock-history me-1"></i>Добавить на позже:
          </div>
          <div class="d-flex flex-column gap-2">
            ${laterItems.slice(0, 3).map(u => `
              <div class="d-flex justify-content-between align-items-center" data-product-id="${u.product_id}" data-name="${escapeHtml(u.name)}" data-price="${u.price_rub}">
                <div style="flex: 1; min-width: 0;">
                  <div class="small text-truncate fw-semibold">${escapeHtml(u.name)}</div>
                  <div class="small text-brand">${formatPrice(u.price_rub)}</div>
                  <div class="small text-muted" style="font-size: 0.65rem;">
                    <i class="bi bi-calendar-event me-1"></i>${escapeHtml(u.next_available)}
                  </div>
                </div>
                <button type="button" class="btn btn-sm btn-outline-secondary rounded-pill px-3" data-action="add" style="font-size: 0.75rem;" title="Добавить в корзину (будет доступно позже)">
                  <i class="bi bi-plus"></i>
                </button>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    // Add Recently Deleted section
    if (recentlyDeleted.length > 0) {
      html += `
        <div class="recently-deleted-section mt-4 px-2">
          <div class="small text-muted text-uppercase fw-bold mb-2 px-1" style="font-size: 0.7rem;">Недавно удаленные:</div>
          <div class="d-flex flex-column gap-1">
            ${recentlyDeleted.map(rd => `
              <div class="d-flex justify-content-between align-items-center py-2 border-bottom border-light opacity-75" data-product-id="${rd.product_id}" data-name="${escapeHtml(rd.name)}" data-price="${rd.price_rub}">
                <div style="flex: 1; min-width: 0;">
                  <div class="small text-truncate text-muted">${escapeHtml(rd.name)}</div>
                </div>
                <button type="button" class="btn btn-sm btn-outline-secondary border-0 rounded-pill px-2" data-action="restore" style="font-size: 0.7rem;">
                  <i class="bi bi-arrow-counterclockwise"></i> Вернуть
                </button>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }
    
    container.innerHTML = html;
    
    // Update totals with delivery fee (only if there are items)
    const currentDeliveryFee = subtotal > 0 ? await getDeliveryFee() : 0;
    const grandTotal = subtotal + currentDeliveryFee;
    
    if (subtotalEl) subtotalEl.textContent = formatPrice(subtotal);
    if (deliveryEl) deliveryEl.textContent = formatPrice(currentDeliveryFee) + (subtotal > 0 ? ' (фиксированная)' : '');
    if (totalEl) totalEl.textContent = formatPrice(grandTotal);
  }
  
  function updateProductControls() {
    // Update quantity controls only on product cards in the menu
    // Use specific selector to avoid affecting cart items or upsell section
    const menuContainer = document.getElementById('menu-container');
    if (!menuContainer) return;
    
    const controls = menuContainer.querySelectorAll('.product-card[data-product-id]');
    controls.forEach(el => {
      const productId = parseInt(el.dataset.productId);
      if (!productId) return;
      
      const qty = getItemQty(productId);
      const qtyDisplay = el.querySelector('.qty-display');
      
      if (qtyDisplay) {
        qtyDisplay.textContent = qty;
      }
      
      // Toggle between "Add" button and quantity controls
      const addBtn = el.querySelector('.btn-add-to-cart');
      const qtyControl = el.querySelector('.product-controls');
      
      if (addBtn && qtyControl) {
        if (qty > 0) {
          addBtn.classList.add('d-none');
          qtyControl.classList.remove('d-none');
          qtyControl.classList.add('d-flex');
          
          // Update button states based on limits
          const plusBtn = qtyControl.querySelector('.qty-btn:last-child');
          if (plusBtn) {
            plusBtn.disabled = qty >= QTY_MAX;
          }
        } else {
          addBtn.classList.remove('d-none');
          qtyControl.classList.add('d-none');
          qtyControl.classList.remove('d-flex');
        }
      }
    });
  }
  
  async function renderCartPage() {
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
    let subtotal = 0;
    
    items.forEach(item => {
      const itemTotal = item.price_rub * item.qty;
      subtotal += itemTotal;
      
      html += `
        <div class="d-flex justify-content-between align-items-center py-2 border-bottom">
          <div style="flex: 1; min-width: 0;">
            <div class="fw-semibold text-truncate">${escapeHtml(item.name)}</div>
            <div class="text-muted small">${formatPrice(item.price_rub)}/шт</div>
          </div>
          <div class="d-flex align-items-center gap-2" style="flex-shrink: 0;">
            <button type="button" class="btn btn-sm btn-outline-secondary rounded-circle" style="width: 32px; height: 32px; padding: 0;"
                    data-action="dec">−</button>
            <span class="fw-semibold" style="min-width: 28px; text-align: center;">${item.qty}</span>
            <button type="button" class="btn btn-sm btn-outline-secondary rounded-circle" style="width: 32px; height: 32px; padding: 0;"
                    data-action="inc"
                    ${item.qty >= QTY_MAX ? 'disabled' : ''}>+</button>
          </div>
          <div class="fw-bold ms-3" style="min-width: 80px; text-align: right;">${formatPrice(itemTotal)}</div>
        </div>
      `;
    });
    
    html += '</div>';
    
    // Calculate totals with delivery fee
    const currentDeliveryFee = await getDeliveryFee();
    const grandTotal = subtotal + currentDeliveryFee;
    
    html += `
      <div class="cart-totals mt-3 pt-3 border-top">
        <div class="d-flex justify-content-between mb-2">
          <span class="text-muted">Итого (товары):</span>
          <span class="fw-semibold">${formatPrice(subtotal)}</span>
        </div>
        <div class="d-flex justify-content-between mb-2">
          <span class="text-muted">Доставка:</span>
          <span class="fw-semibold">${formatPrice(currentDeliveryFee)} (фиксированная)</span>
        </div>
        <div class="d-flex justify-content-between fw-bold h5 mb-0 mt-2 pt-2 border-top">
          <span>Итого к оплате:</span>
          <span class="text-brand">${formatPrice(grandTotal)}</span>
        </div>
      </div>
    `;
    
    container.innerHTML = html;
  }
  
  async function updateCheckoutTotal() {
    const subtotalEl = document.getElementById('checkoutSubtotal');
    const deliveryEl = document.getElementById('checkoutDeliveryFee');
    const grandTotalEl = document.getElementById('checkoutGrandTotal');
    
    if (subtotalEl || deliveryEl || grandTotalEl) {
      const items = loadCart();
      const subtotal = getTotalPrice(items);
      const currentDeliveryFee = await getDeliveryFee();
      const grandTotal = subtotal + currentDeliveryFee;
      
      if (subtotalEl) subtotalEl.textContent = formatPrice(subtotal);
      if (deliveryEl) deliveryEl.textContent = formatPrice(currentDeliveryFee) + ' (фиксированная)';
      if (grandTotalEl) grandTotalEl.textContent = formatPrice(grandTotal);
    }
  }

  function renderRecentlyDeletedOnCheckout() {
    const container = document.getElementById('recentlyDeletedList');
    if (!container) return;

    if (recentlyDeleted.length === 0) {
      container.innerHTML = '';
      const section = container.closest('.recently-deleted-section');
      if (section) section.style.display = 'none';
      return;
    }

    const section = container.closest('.recently-deleted-section');
    if (section) section.style.display = 'block';

    let html = '';
    recentlyDeleted.forEach(rd => {
      html += `
        <div class="d-flex justify-content-between align-items-center py-2 border-bottom border-light opacity-75" data-product-id="${rd.product_id}" data-name="${escapeHtml(rd.name)}" data-price="${rd.price_rub}">
          <div style="flex: 1; min-width: 0;">
            <div class="small text-truncate text-muted">${escapeHtml(rd.name)}</div>
          </div>
          <button type="button" class="btn btn-sm btn-outline-secondary border-0 rounded-pill px-2" data-action="restore" style="font-size: 0.7rem;">
            <i class="bi bi-arrow-counterclockwise"></i> Вернуть
          </button>
        </div>
      `;
    });

    container.innerHTML = html;

    // Add event listeners for restore buttons
    container.querySelectorAll('[data-action="restore"]').forEach(btn => {
      btn.addEventListener('click', function(e) {
        const itemEl = e.target.closest('[data-product-id]');
        if (!itemEl) return;

        const productId = parseInt(itemEl.dataset.productId);
        const price = parseInt(itemEl.dataset.price);
        const name = itemEl.dataset.name;

        addItem(productId, price, name);
      });
    });
  }

  function renderRecentlyDeletedOnCart() {
    const section = document.getElementById('recentlyDeletedSection');
    const container = document.getElementById('recentlyDeletedList');
    if (!container || !section) return;

    if (recentlyDeleted.length === 0) {
      section.classList.add('d-none');
      return;
    }

    section.classList.remove('d-none');

    let html = '';
    recentlyDeleted.slice(0, 3).forEach(rd => {
      html += `
        <div class="d-flex justify-content-between align-items-center py-2 border-bottom border-light opacity-75" data-product-id="${rd.product_id}" data-name="${escapeHtml(rd.name)}" data-price="${rd.price_rub}">
          <div style="flex: 1; min-width: 0;">
            <div class="small text-truncate text-muted">${escapeHtml(rd.name)}</div>
          </div>
          <button type="button" class="btn btn-sm btn-outline-secondary border-0 rounded-pill px-2" data-action="restore" style="font-size: 0.7rem;">
            <i class="bi bi-arrow-counterclockwise"></i> Вернуть
          </button>
        </div>
      `;
    });

    container.innerHTML = html;

    // Add event listeners for restore buttons
    container.querySelectorAll('[data-action="restore"]').forEach(btn => {
      btn.addEventListener('click', function(e) {
        const itemEl = e.target.closest('[data-product-id]');
        if (!itemEl) return;

        const productId = parseInt(itemEl.dataset.productId);
        const price = parseInt(itemEl.dataset.price);
        const name = itemEl.dataset.name;

        addItem(productId, price, name);
      });
    });
  }
  
  async function updateAllUI() {
    await updateNavbarCart();
    await updateOffcanvasCart();
    updateProductControls();
    await renderCartPage();
    await updateCheckoutTotal();
    renderRecentlyDeletedOnCheckout();
    renderRecentlyDeletedOnCart();
  }
  
  // Toast Notifications Queue System
  const toastQueue = [];
  let activeToasts = [];
  const MAX_TOASTS = 3;
  const TOAST_DURATION = 4000;
  
  function showToast(message, type = 'info', showCartSummary = false) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    toastQueue.push({ message, type, showCartSummary, timestamp: Date.now() });
    processToastQueue();
  }
  
  function showUndoToast(message, undoCallback) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const toastId = 'undoToast' + Date.now();
    const toastEl = document.createElement('div');
    toastEl.className = 'toast show';
    toastEl.id = toastId;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');
    toastEl.style.cssText = 'position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); z-index: 9999; min-width: 280px; background: var(--color-bg-primary); border: 1px solid var(--color-accent-border); border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);';
    
    toastEl.innerHTML = `
      <div class="toast-body d-flex justify-content-between align-items-center p-3">
        <span class="text-muted">${escapeHtml(message)}</span>
        <button type="button" class="btn btn-sm btn-link text-brand p-0 ms-3 fw-semibold" style="text-decoration: none;">
          Отменить
        </button>
      </div>
    `;
    
    container.appendChild(toastEl);
    
    const undoBtn = toastEl.querySelector('button');
    if (undoBtn && undoCallback) {
      undoBtn.addEventListener('click', () => {
        undoCallback();
        toastEl.classList.remove('show');
        setTimeout(() => toastEl.remove(), 300);
      });
    }
    
    setTimeout(() => {
      toastEl.classList.remove('show');
      setTimeout(() => toastEl.remove(), 300);
    }, 5000);
  }
  
  function processToastQueue() {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    // Remove expired toasts from active list
    activeToasts = activeToasts.filter(toast => {
      if (Date.now() - toast.timestamp > TOAST_DURATION) {
        if (toast.element && toast.element.parentNode) {
          toast.element.classList.remove('show');
          setTimeout(() => {
            if (toast.element && toast.element.parentNode) {
              toast.element.remove();
            }
          }, 300);
        }
        if (toast.timeoutId) {
          clearTimeout(toast.timeoutId);
        }
        return false;
      }
      return true;
    });
    
    // Process queue if space available
    while (toastQueue.length > 0 && activeToasts.length < MAX_TOASTS) {
      const toastData = toastQueue.shift();
      createAndShowToast(toastData, container);
    }
  }
  
  function createAndShowToast(toastData, container) {
    const { message, type, showCartSummary } = toastData;
    const toastId = 'cartToast' + Date.now() + '_' + Math.random().toString(36).substr(2, 5);
    
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
    
    const toastEl = document.createElement('div');
    toastEl.className = 'toast show';
    toastEl.id = toastId;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');
    
    toastEl.innerHTML = `
      <div class="toast-header">
        <i class="bi bi-${icon} me-2"></i>
        <strong class="me-auto">Корзина обновлена</strong>
        <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
      <div class="toast-body">
        ${escapeHtml(message)}
      </div>
    `;
    
    container.appendChild(toastEl);
    
    // Setup close button
    const closeBtn = toastEl.querySelector('.btn-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        toastEl.classList.remove('show');
        setTimeout(() => {
          if (toastEl.parentNode) {
            toastEl.remove();
          }
          removeFromActiveToasts(toastId);
        }, 300);
      });
    }
    
    // Auto-hide
    const timeoutId = setTimeout(() => {
      toastEl.classList.remove('show');
      setTimeout(() => {
        if (toastEl.parentNode) {
          toastEl.remove();
        }
        removeFromActiveToasts(toastId);
        processToastQueue();
      }, 300);
    }, TOAST_DURATION);
    
    // Track active toast
    activeToasts.push({
      id: toastId,
      element: toastEl,
      timeoutId: timeoutId,
      timestamp: Date.now()
    });
  }
  
  function removeFromActiveToasts(toastId) {
    const index = activeToasts.findIndex(t => t.id === toastId);
    if (index > -1) {
      const toast = activeToasts[index];
      if (toast.timeoutId) {
        clearTimeout(toast.timeoutId);
      }
      activeToasts.splice(index, 1);
    }
  }
  
  // Event Handlers
  let _eventsSetup = false;
  function setupEventListeners() {
    if (_eventsSetup) return;
    _eventsSetup = true;
    
    // Offcanvas clear button
    const clearBtn = document.getElementById('offcanvasClearBtn');
    if (clearBtn) {
      clearBtn.addEventListener('click', function() {
        clearCart();
      });
    }

    // Offcanvas Actions Delegation
    const offcanvasBody = document.getElementById('offcanvasCartBody');
    if (offcanvasBody) {
      offcanvasBody.addEventListener('click', (e) => {
        const target = e.target.closest('[data-action]');
        if (!target) return;

        const action = target.dataset.action;
        const itemEl = target.closest('[data-product-id]');
        if (!itemEl) return;

        const productId = parseInt(itemEl.dataset.productId);
        const price = parseInt(itemEl.dataset.price);
        const name = itemEl.dataset.name;

        switch (action) {
          case 'inc':
            updateQty(productId, 1);
            break;
          case 'dec':
            updateQty(productId, -1);
            break;
          case 'remove':
            removeItem(productId);
            break;
          case 'add':
          case 'restore':
            addItem(productId, price, name);
            break;
        }
      });
    }
    
    // Setup offcanvas instance
    const offcanvasEl = document.getElementById('offcanvasCart');
    if (offcanvasEl && typeof bootstrap !== 'undefined') {
      offcanvasInstance = bootstrap.Offcanvas.getOrCreateInstance(offcanvasEl);
    }

    // Checkout page recently deleted section
    const recentlyDeletedList = document.getElementById('recentlyDeletedList');
    if (recentlyDeletedList) {
      recentlyDeletedList.addEventListener('click', (e) => {
        const target = e.target.closest('[data-action]');
        if (!target) return;

        const action = target.dataset.action;
        if (action !== 'restore') return;

        const itemEl = target.closest('[data-product-id]');
        if (!itemEl) return;

        const productId = parseInt(itemEl.dataset.productId);
        const price = parseInt(itemEl.dataset.price);
        const name = itemEl.dataset.name;

        addItem(productId, price, name);
      });
    }
  }
  
  // Add for later items storage
  let addForLaterItems = [];

  function setAddForLaterItems(items) {
    addForLaterItems = items || [];
    updateAllUI();
  }

  function getAddForLaterItems() {
    return addForLaterItems;
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
    undoClearCart: undoClearCart,
    getItemQty: getItemQty,
    getItems: getItems,
    loadCart: loadCart,
    
    // UI updates
    updateAllUI: updateAllUI,
    updateProductControls: updateProductControls,
    renderCartPage: renderCartPage,
    updateCheckoutTotal: updateCheckoutTotal,
    renderRecentlyDeletedOnCheckout: renderRecentlyDeletedOnCheckout,
    renderRecentlyDeletedOnCart: renderRecentlyDeletedOnCart,
    showToast: showToast,
    setUpsellSuggestions: function(items) {
      upsellSuggestions.length = 0;
      upsellSuggestions.push(...items);
      updateAllUI();
    },
    
    // Add for later
    setAddForLaterItems: setAddForLaterItems,
    getAddForLaterItems: getAddForLaterItems,
    
    // Delivery fee
    getDeliveryFee: getDeliveryFee,
    
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
  CartManager.renderRecentlyDeletedOnCart();
}

function initCheckoutPage() {
  CartManager.renderCartPage();
  CartManager.updateCheckoutTotal();
  CartManager.renderRecentlyDeletedOnCheckout();
  setupCheckoutForm();
}

function generateIdempotencyKey() {
  if (typeof window.crypto !== 'undefined' && typeof window.crypto.randomUUID === 'function') {
    return window.crypto.randomUUID();
  }
  if (typeof window.crypto !== 'undefined' && typeof window.crypto.getRandomValues === 'function') {
    const array = new Uint32Array(4);
    window.crypto.getRandomValues(array);
    const hex = Array.from(array, (n) => n.toString(16).padStart(8, '0')).join('');
    return hex.substring(0, 8) + '-' + hex.substring(8, 12) + '-4' + hex.substring(13, 16) + '-a' + hex.substring(17, 20) + '-' + hex.substring(20, 32);
  }
  console.error('Crypto API is not available - idempotency protection disabled');
  return 'fallback_' + Date.now() + '_' + Math.random().toString(36).substring(2, 11);
}

function validatePhone(phone) {
  // Basic phone validation for Russian numbers
  const cleanPhone = phone.replace(/\D/g, '');
  // Should start with 7 or 8 and have 11 digits total
  return /^[78]\d{10}$/.test(cleanPhone);
}

function setupCheckoutForm() {
  const form = document.getElementById('orderForm');
  if (!form) return;
  
  form.addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const items = CartManager.loadCart();
    if (items.length === 0) {
      CartManager.showToast('Корзина пуста', 'warning');
      return;
    }
    
    const submitBtn = document.getElementById('submitBtn');
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Оформляем...';
    
    // Clear any previous errors
    const errorDiv = document.getElementById('formError');
    if (errorDiv) {
      errorDiv.classList.add('d-none');
    }
    
    const deliveryMode = document.querySelector('input[name="delivery_mode"]:checked').value;
    
    const sanitizeInput = (str) => {
      if (!str) return '';
      return String(str)
        .replace(/[<>{}\\/]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
    };
    
    const name = sanitizeInput(document.getElementById('name').value);
    const phone = sanitizeInput(document.getElementById('phone').value);
    const address = sanitizeInput(document.getElementById('address').value);
    
    // Client-side validation
    if (name.length < 2) {
      CartManager.showToast('Введите корректное имя', 'warning');
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalText;
      return;
    }
    
    if (!validatePhone(phone)) {
      CartManager.showToast('Введите корректный номер телефона (+7XXXXXXXXXX)', 'warning');
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalText;
      return;
    }
    
    if (address.length < 8) {
      CartManager.showToast('Введите полный адрес доставки', 'warning');
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalText;
      return;
    }
    
    const formData = {
      name: name,
      phone: phone,
      address: address,
      comment: sanitizeInput(document.getElementById('comment').value) || null,
      delivery_mode: deliveryMode,
      delivery_slot: null,
      delivery_date: null,
      payment_method: document.querySelector('input[name="payment_method"]:checked').value,
      items: items.map(item => ({
        product_id: item.product_id,
        qty: item.qty
      })),
      idempotency_key: generateIdempotencyKey(),
      client_max_uid: (() => {
        const uid = new URLSearchParams(window.location.search).get('max_uid');
        return uid ? parseInt(uid, 10) || null : null;
      })()
    };
    
    if (deliveryMode === 'slot') {
      formData.delivery_slot = document.getElementById('slot_time_select').value;
      formData.delivery_date = document.getElementById('delivery_date').value;
      
      if (!formData.delivery_slot) {
        CartManager.showToast('Выберите время доставки', 'warning');
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
        return;
      }
      
      if (!formData.delivery_date) {
        CartManager.showToast('Выберите дату доставки', 'warning');
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
        localStorage.setItem("cart", "[]");
        if (data.confirmation_token) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalText;
          showYooKassaWidget(data.confirmation_token, data.order_id);
        } else {
          window.location.href = `/thanks/${data.order_id}`;
      }
      
      } else {
        const errorMsg = data.detail || 'Ошибка при оформлении заказа';
        CartManager.showToast(errorMsg, 'error');
        // Also show in form error div for better visibility
        if (errorDiv) {
          errorDiv.textContent = errorMsg;
          errorDiv.classList.remove('d-none');
        }
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
      }
    } catch (error) {
      console.error('Error:', error);
      CartManager.showToast('Ошибка соединения. Попробуйте позже.', 'error');
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalText;
    }
  });
}

function showError(message) {
  // Legacy function - now uses toast notifications
  CartManager.showToast(message, 'error');
  // Keep fallback to form error div
  const errorDiv = document.getElementById('formError');
  if (errorDiv) {
    errorDiv.textContent = message;
    errorDiv.classList.remove('d-none');
  }
}

function showYooKassaWidget(confirmationToken, orderId) {
  // Динамически загружаем CDN виджета, если ещё не загружен
  function _renderWidget() {
    // Создаём контейнер если нет
    let container = document.getElementById('yookassa-widget-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'yookassa-widget-container';
      container.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;';
      const inner = document.createElement('div');
      inner.id = 'payment-form';
      inner.style.cssText = 'background:#fff;border-radius:12px;padding:24px;width:100%;max-width:480px;max-height:90vh;overflow:auto;';
      container.appendChild(inner);
      document.body.appendChild(container);
    }

    const checkout = new window.YooMoneyCheckoutWidget({
      confirmation_token: confirmationToken,
      return_url: `${window.location.origin}/thanks/${orderId}`,
      customization: {
        payment_methods: ['bank_card', 'sbp']
      },
      error_callback(error) {
        console.error('YooKassa widget error:', error);
        CartManager.showToast('Ошибка платёжного виджета. Попробуйте позже.', 'error');
      },
    });

    checkout.render('payment-form').then(() => {
      checkout.on('success', () => {
        checkout.destroy();
        document.getElementById('yookassa-widget-container')?.remove();
        window.location.href = `/thanks/${orderId}`;
      });
      checkout.on('fail', () => {
        checkout.destroy();
        document.getElementById('yookassa-widget-container')?.remove();
        CartManager.showToast('Оплата не прошла. Попробуйте ещё раз.', 'error');
      });
    });
  }

  if (window.YooMoneyCheckoutWidget) {
    _renderWidget();
  } else {
    const script = document.createElement('script');
    script.src = 'https://yookassa.ru/checkout-widget/v1/checkout-widget.js';
    script.onload = _renderWidget;
    script.onerror = () => CartManager.showToast('Не удалось загрузить платёжный виджет.', 'error');
    document.head.appendChild(script);
  }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
  CartManager.init();
});
