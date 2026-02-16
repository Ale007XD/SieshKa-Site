/**
 * Time-First Menu System - Frontend
 * Handles slots, availability, sticky bar, and dynamic menu updates
 * Updated to use unified CartManager
 */

// Global state
const MenuState = {
    day: 'today',
    method: 'delivery',
    selectedSlot: null,
    slots: [],
    menuData: null
};

// Constants
const DAY_LABELS = {
    today: 'Сегодня',
    tomorrow: 'Завтра'
};

const METHOD_LABELS = {
    delivery: 'Доставка',
    pickup: 'Самовывоз'
};

const REASON_LABELS = {
    OUTSIDE_WINDOW: 'Вне времени приема заказов',
    LEAD_TIME: 'Требуется предзаказ',
    METHOD_NOT_ALLOWED: 'Недоступно для этого способа',
    TOMORROW_CUTOFF: 'Заказы на завтра до 23:00',
    INACTIVE: 'Временно недоступно',
    NO_RULE: 'Нет правил доступности'
};

const CTA_LABELS = {
    add_to_cart: 'Добавить',
    select_time: 'Выбрать время',
    preorder: 'Предзаказ',
    unavailable: 'Недоступно'
};

// ============================================================================
// Initialization
// ============================================================================

function waitForCartManager(callback) {
    if (typeof CartManager !== 'undefined') {
        callback();
    } else {
        setTimeout(() => waitForCartManager(callback), 50);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initStickyBar();
    loadSlots();
    loadMenu();
    
    // Wait for CartManager and setup event delegation
    waitForCartManager(() => {
        setupProductEventDelegation();
        syncAllProductControls();
    });
});

// ============================================================================
// Event Delegation for Cart Actions
// ============================================================================

function setupProductEventDelegation() {
    const menuContainer = document.getElementById('menu-container');
    if (!menuContainer) return;
    
    menuContainer.addEventListener('click', (e) => {
        const addBtn = e.target.closest('.btn-add-to-cart');
        const qtyBtn = e.target.closest('.qty-btn');
        
        // Handle Add to Cart buttons
        if (addBtn) {
            e.preventDefault();
            const productCard = addBtn.closest('[data-product-id]');
            
            // Check for preorder action
            if (addBtn.dataset.action === 'preorder') {
                showPreorderInfo(parseInt(addBtn.dataset.productId));
                return;
            }
            
            // Check for scroll to slot action
            if (addBtn.dataset.action === 'scroll-slot') {
                scrollToSlotSelector();
                return;
            }
            
            // Standard add to cart
            if (productCard) {
                const productId = parseInt(productCard.dataset.productId);
                const price = parseInt(productCard.dataset.price);
                const name = productCard.dataset.name;
                addToCartWithQty(productId, price, name);
            }
        }
        
        // Handle Quantity +/- buttons
        if (qtyBtn) {
            e.preventDefault();
            const productCard = qtyBtn.closest('[data-product-id]');
            if (productCard) {
                const productId = parseInt(productCard.dataset.productId);
                const delta = qtyBtn.classList.contains('qty-btn-minus') ? -1 : 1;
                updateProductQty(productId, delta);
            }
        }
    });
}

// ============================================================================
// Sticky Bar
// ============================================================================

function initStickyBar() {
    const stickyBar = document.getElementById('sticky-bar');
    if (!stickyBar) return;
    
    // Day toggle
    const dayButtons = stickyBar.querySelectorAll('[data-day]');
    dayButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const day = btn.dataset.day;
            setDay(day);
            
            // Update active state
            dayButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
    
    // Method toggle
    const methodButtons = stickyBar.querySelectorAll('[data-method]');
    methodButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const method = btn.dataset.method;
            setMethod(method);
            
            // Update active state
            methodButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
    
    // Slot selector
    const slotSelect = document.getElementById('slot-select');
    if (slotSelect) {
        slotSelect.addEventListener('change', (e) => {
            setSlot(e.target.value || null);
        });
    }
}

function setDay(day) {
    MenuState.day = day;
    loadSlots();
    loadMenu();
    updateStickyBarUI();
}

function setMethod(method) {
    MenuState.method = method;
    loadSlots();
    loadMenu();
    updateStickyBarUI();
}

function setSlot(slot) {
    MenuState.selectedSlot = slot;
    loadMenu();
}

function updateStickyBarUI() {
    // Update button states
    document.querySelectorAll('[data-day]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.day === MenuState.day);
    });
    
    document.querySelectorAll('[data-method]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.method === MenuState.method);
    });
    
    // Update slot select
    const slotSelect = document.getElementById('slot-select');
    if (slotSelect && MenuState.slots.length > 0) {
        const currentValue = slotSelect.value;
        slotSelect.innerHTML = '<option value="">Как можно скорее</option>';
        
        MenuState.slots.forEach(slot => {
            const option = document.createElement('option');
            option.value = slot.time;
            option.textContent = slot.label;
            option.disabled = !slot.available;
            slotSelect.appendChild(option);
        });
        
        // Restore selection if still valid
        if (currentValue) {
            slotSelect.value = currentValue;
        }
    }
}

// ============================================================================
// API Calls
// ============================================================================

async function loadSlots() {
    try {
        const response = await fetch(
            `/api/slots?day=${MenuState.day}&method=${MenuState.method}`
        );
        
        if (!response.ok) throw new Error('Failed to load slots');
        
        const data = await response.json();
        MenuState.slots = data.slots || [];
        
        if (data.error) {
            showNotification(data.error, 'warning');
        }
        
        updateStickyBarUI();
    } catch (error) {
        console.error('Error loading slots:', error);
    }
}

async function loadMenu() {
    try {
        let url = `/api/menu?day=${MenuState.day}&method=${MenuState.method}`;
        if (MenuState.selectedSlot) {
            url += `&slot=${MenuState.selectedSlot}`;
        }
        
        const response = await fetch(url);
        
        if (!response.ok) throw new Error('Failed to load menu');
        
        const data = await response.json();
        MenuState.menuData = data;
        renderMenu(data);
        
        // Sync product controls after rendering
        if (typeof CartManager !== 'undefined') {
            setTimeout(() => CartManager.updateProductControls(), 0);
        }
    } catch (error) {
        console.error('Error loading menu:', error);
        const container = document.getElementById('menu-container');
        if (container) {
            container.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Ошибка загрузки меню. Пожалуйста, попробуйте позже.
                </div>
            `;
        }
    }
}

// ============================================================================
// Menu Rendering
// ============================================================================

function renderMenu(data) {
    const container = document.getElementById('menu-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (!data.categories || data.categories.length === 0) {
        container.innerHTML = `
            <div class="alert alert-info">
                <i class="bi bi-info-circle me-2"></i>
                Меню временно недоступно
            </div>
        `;
        return;
    }
    
    data.categories.forEach(category => {
        const categoryEl = createCategoryElement(category);
        container.appendChild(categoryEl);
    });
}

function createCategoryElement(category) {
    const section = document.createElement('section');
    section.className = 'menu-category mb-5';
    section.id = `category-${category.category_id}`;
    
    const header = document.createElement('h2');
    header.className = 'h4 mb-3';
    header.textContent = category.name;
    section.appendChild(header);
    
    const productsGrid = document.createElement('div');
    productsGrid.className = 'row g-3';
    
    category.products.forEach(product => {
        const productEl = createProductElement(product);
        productsGrid.appendChild(productEl);
    });
    
    section.appendChild(productsGrid);
    return section;
}

function createProductElement(product) {
    const col = document.createElement('div');
    col.className = 'col-6 col-md-4 col-lg-3';
    
    const isAvailable = product.available;
    const ctaType = product.cta_type;
    
    // Build product card with data attributes for cart integration
    col.innerHTML = `
        <div class="card h-100 product-card ${isAvailable ? '' : 'unavailable'}" 
             data-product-id="${product.product_id}"
             data-name="${escapeHtml(product.name)}"
             data-price="${product.price_rub}"
             data-available="${isAvailable}">
            <div class="card-body">
                <h5 class="card-title h6">${escapeHtml(product.name)}</h5>
                <p class="card-text">
                    <span class="price">${product.price_rub} ₽</span>
                </p>
                
                ${product.badge_text ? `
                    <span class="badge ${isAvailable ? 'bg-success' : 'bg-secondary'}">
                        ${escapeHtml(product.badge_text)}
                    </span>
                ` : ''}
                
                ${product.next_available ? `
                    <small class="d-block text-muted mt-1">
                        ${escapeHtml(product.next_available)}
                    </small>
                ` : ''}
                
                ${product.reason_code ? `
                    <small class="d-block text-muted mt-1 reason-code">
                        ${REASON_LABELS[product.reason_code] || product.reason_code}
                    </small>
                ` : ''}
            </div>
            
            <div class="card-footer">
                ${renderProductControls(product, isAvailable, ctaType)}
            </div>
        </div>
    `;
    
    // Add event listeners for quantity controls
    setupProductControls(col, product, isAvailable, ctaType);
    
    return col;
}

function renderProductControls(product, isAvailable, ctaType) {
    if (!isAvailable) {
        return `
            <button class="btn btn-unavailable btn-sm" disabled>
                ${CTA_LABELS[ctaType] || 'Недоступно'}
            </button>
        `;
    }
    
    if (ctaType === 'select_time') {
        return `
            <button class="btn btn-outline-brand btn-add-to-cart btn-sm" 
                    data-action="scroll-slot">
                ${CTA_LABELS[ctaType]}
            </button>
        `;
    }
    
    if (ctaType === 'preorder') {
        return `
            <button class="btn btn-outline-brand btn-add-to-cart btn-sm" 
                    data-action="preorder" data-product-id="${product.product_id}">
                ${CTA_LABELS[ctaType]}
            </button>
        `;
    }
    
    // Default: add to cart with quantity controls
    const productId = product.product_id;
    const priceRub = product.price_rub;
    const name = product.name; // Will be read from data attribute
    
    return `
        <div class="product-controls" data-product-id="${productId}" data-price="${priceRub}" data-name="${escapeHtml(name)}">
            <button class="btn btn-brand btn-add-to-cart btn-sm" 
                    id="add-btn-${productId}"
                    ${!isAvailable ? 'disabled' : ''}>
                <i class="bi bi-plus-lg me-1"></i>Добавить
            </button>
            
            <div class="qty-control-group d-none" id="qty-control-${productId}">
                <button type="button" class="qty-btn qty-btn-minus" 
                        aria-label="Уменьшить количество">
                    −
                </button>
                <span class="qty-display" id="qty-display-${productId}">0</span>
                <button type="button" class="qty-btn" 
                        aria-label="Увеличить количество">
                    +
                </button>
            </div>
        </div>
    `;
}

function setupProductControls(col, product, isAvailable, ctaType) {
    // Now handled by syncAllProductControls() after CartManager is ready
}

// ============================================================================
// Cart Integration Functions
// ============================================================================

function addToCartWithQty(productId, priceRub, name) {
    if (typeof CartManager === 'undefined') {
        console.error('CartManager not loaded');
        return;
    }
    
    // Add item to cart
    const success = CartManager.addItem(productId, priceRub, name);
    
    if (success) {
        // Update UI to show quantity controls
        syncProductControl(productId);
        
        // Trigger cart animation in navbar
        triggerCartAnimation();
    }
}

function updateProductQty(productId, delta) {
    if (typeof CartManager === 'undefined') {
        console.error('CartManager not loaded');
        return;
    }
    
    const success = CartManager.updateQty(productId, delta);
    
    if (success) {
        syncProductControl(productId);
    }
}

function syncProductControl(productId) {
    if (typeof CartManager === 'undefined') return;
    
    const qty = CartManager.getItemQty(productId);
    const addBtn = document.getElementById(`add-btn-${productId}`);
    const qtyControl = document.getElementById(`qty-control-${productId}`);
    const qtyDisplay = document.getElementById(`qty-display-${productId}`);
    
    if (!addBtn || !qtyControl) return;
    
    if (qty > 0) {
        addBtn.classList.add('d-none');
        qtyControl.classList.remove('d-none');
        if (qtyDisplay) {
            qtyDisplay.textContent = qty;
        }
        
        // Update button states based on limits
        const plusBtn = qtyControl.querySelector('.qty-btn:last-child');
        if (plusBtn) {
            plusBtn.disabled = qty >= CartManager.QTY_MAX;
        }
    } else {
        addBtn.classList.remove('d-none');
        qtyControl.classList.add('d-none');
    }
}

function syncAllProductControls() {
    if (typeof CartManager === 'undefined') return;
    
    document.querySelectorAll('[data-product-id]').forEach(card => {
        const productId = parseInt(card.dataset.productId);
        if (productId) {
            syncProductControl(productId);
        }
    });
}

// ============================================================================
// UI Helpers
// ============================================================================

function scrollToSlotSelector() {
    const selector = document.getElementById('slot-select');
    if (selector) {
        selector.scrollIntoView({ behavior: 'smooth', block: 'center' });
        selector.focus();
        
        // Highlight the selector temporarily
        selector.classList.add('is-invalid');
        setTimeout(() => selector.classList.remove('is-invalid'), 1000);
    }
}

function showPreorderInfo(productId) {
    showNotification(
        'Этот товар требует предзаказа минимум за 3 часа. Выберите время доставки.',
        'info'
    );
}

function triggerCartAnimation() {
    const cartBtn = document.getElementById('navbarCartBtn');
    if (cartBtn) {
        cartBtn.classList.add('bounce');
        setTimeout(() => cartBtn.classList.remove('bounce'), 500);
    }
}

function showNotification(message, type = 'info') {
    // Use CartManager toast if available
    if (typeof CartManager !== 'undefined' && CartManager.showToast) {
        CartManager.showToast(message, type);
        return;
    }
    
    // Fallback to simple notification
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 80px; right: 20px; z-index: 9999; max-width: 300px;';
    notification.innerHTML = `
        ${escapeHtml(message)}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// ============================================================================
// Utilities
// ============================================================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeJs(text) {
    if (!text) return '';
    return String(text)
        .replace(/'/g, "\\'")
        .replace(/"/g, '\\"');
}

// Expose necessary functions globally
window.addToCartWithQty = addToCartWithQty;
window.updateProductQty = updateProductQty;
window.scrollToSlotSelector = scrollToSlotSelector;
window.showPreorderInfo = showPreorderInfo;
