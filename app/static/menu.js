/**
 * Time-First Menu System - Frontend
 * Handles slots, availability, sticky bar, and dynamic menu updates
 */

// Global state
const MenuState = {
    day: 'today',
    method: 'delivery',
    selectedSlot: null,
    slots: [],
    menuData: null,
    cart: {}
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
    add_to_cart: 'В корзину',
    select_time: 'Выбрать время',
    preorder: 'Предзаказ',
    unavailable: 'Недоступно'
};

// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initStickyBar();
    loadSlots();
    loadMenu();
    updateCartDisplay();
});

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
    } catch (error) {
        console.error('Error loading menu:', error);
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
        container.innerHTML = '<div class="alert alert-info">Меню временно недоступно</div>';
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
    
    col.innerHTML = `
        <div class="card h-100 product-card ${isAvailable ? '' : 'unavailable'}">
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
            
            <div class="card-footer bg-transparent border-0">
                ${renderProductButton(product)}
            </div>
        </div>
    `;
    
    return col;
}

function renderProductButton(product) {
    const ctaType = product.cta_type;
    const label = CTA_LABELS[ctaType] || 'Добавить';
    
    switch (ctaType) {
        case 'add_to_cart':
            return `
                <button class="btn btn-primary w-100" 
                        onclick="addToCart(${product.product_id}, '${escapeJs(product.name)}', ${product.price_rub})">
                    ${label}
                </button>
            `;
        
        case 'select_time':
            return `
                <button class="btn btn-outline-primary w-100" 
                        onclick="scrollToSlotSelector()">
                    ${label}
                </button>
            `;
        
        case 'preorder':
            return `
                <button class="btn btn-outline-warning w-100" 
                        onclick="showPreorderInfo(${product.product_id})">
                    ${label}
                </button>
            `;
        
        case 'unavailable':
        default:
            return `
                <button class="btn btn-secondary w-100" disabled>
                    ${label}
                </button>
            `;
    }
}

// ============================================================================
// Cart Functions
// ============================================================================

function addToCart(productId, name, price) {
    const key = `${MenuState.day}:${MenuState.method}:${MenuState.selectedSlot || 'asap'}:${productId}`;
    
    if (!MenuState.cart[key]) {
        MenuState.cart[key] = {
            productId,
            name,
            price,
            qty: 0,
            day: MenuState.day,
            method: MenuState.method,
            slot: MenuState.selectedSlot
        };
    }
    
    MenuState.cart[key].qty += 1;
    
    saveCart();
    updateCartDisplay();
    showNotification(`${escapeHtml(name)} добавлен в корзину`, 'success');
    
    // Trigger cart animation
    triggerCartAnimation();
}

function removeFromCart(key) {
    delete MenuState.cart[key];
    saveCart();
    updateCartDisplay();
}

function updateCartQty(key, delta) {
    if (!MenuState.cart[key]) return;
    
    MenuState.cart[key].qty += delta;
    
    if (MenuState.cart[key].qty <= 0) {
        removeFromCart(key);
    } else {
        saveCart();
        updateCartDisplay();
    }
}

function saveCart() {
    localStorage.setItem('timefirst_cart', JSON.stringify(MenuState.cart));
}

function loadCart() {
    try {
        const saved = localStorage.getItem('timefirst_cart');
        if (saved) {
            MenuState.cart = JSON.parse(saved);
        }
    } catch (e) {
        console.error('Error loading cart:', e);
    }
}

function updateCartDisplay() {
    const cartCount = Object.values(MenuState.cart).reduce((sum, item) => sum + item.qty, 0);
    const cartTotal = Object.values(MenuState.cart).reduce((sum, item) => sum + (item.price * item.qty), 0);
    
    // Update cart badge
    const badge = document.getElementById('cart-badge');
    if (badge) {
        badge.textContent = cartCount;
        badge.style.display = cartCount > 0 ? 'inline' : 'none';
    }
    
    // Update cart button
    const cartBtn = document.getElementById('cart-btn');
    if (cartBtn) {
        cartBtn.textContent = `Корзина (${cartCount}) • ${cartTotal} ₽`;
    }
}

// ============================================================================
// UI Helpers
// ============================================================================

function scrollToSlotSelector() {
    const selector = document.getElementById('slot-select');
    if (selector) {
        selector.scrollIntoView({ behavior: 'smooth', block: 'center' });
        selector.focus();
    }
}

function showPreorderInfo(productId) {
    showNotification(
        'Этот товар требует предзаказа минимум за 3 часа. Выберите время доставки.',
        'info'
    );
}

function triggerCartAnimation() {
    const cartBtn = document.getElementById('cart-btn');
    if (cartBtn) {
        cartBtn.classList.add('bounce');
        setTimeout(() => cartBtn.classList.remove('bounce'), 500);
    }
}

function showNotification(message, type = 'info') {
    // Simple notification - can be replaced with a toast library
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
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeJs(text) {
    return text.replace(/'/g, "\\'").replace(/"/g, '\\"');
}

// Initialize cart on load
loadCart();
