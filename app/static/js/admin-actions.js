(function() {
    'use strict';

    function getSelectedPks() {
        const selected = [];

        document.querySelectorAll('input[name="pks"], input[data-pk]:checked, input[type="checkbox"][value]:checked').forEach(function(el) {
            if (el.name === 'pks' && el.checked && el.value) {
                selected.push(el.value);
                return;
            }

            if (el.dataset.pk) {
                selected.push(el.dataset.pk);
                return;
            }

            if (el.checked && el.value && el.value !== 'on') {
                selected.push(el.value);
            }
        });

        return [...new Set(selected)].join(',');
    }

    async function postJson(endpoint, payload) {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const contentType = response.headers.get('content-type') || '';

        if (contentType.includes('application/json')) {
            return await response.json();
        }

        if (response.redirected || response.ok) {
            return { success: true };
        }

        return { success: false, error: 'Неожиданный ответ сервера' };
    }

    async function postForm(endpoint, formData) {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
            body: new URLSearchParams(formData).toString()
        });

        const contentType = response.headers.get('content-type') || '';

        if (contentType.includes('application/json')) {
            return await response.json();
        }

        if (response.redirected || response.ok) {
            return { success: true };
        }

        return { success: false, error: 'Неожиданный ответ сервера' };
    }

    function initAdminActions() {
        document.body.addEventListener('click', async function(e) {
            const btn = e.target.closest('[data-admin-action]');
            if (!btn) return;

            e.preventDefault();

            const action = btn.dataset.adminAction;
            const confirmMsg = btn.dataset.confirmMessage;
            const payload = btn.dataset.payload ? JSON.parse(btn.dataset.payload) : {};

            if (confirmMsg && !confirm(confirmMsg)) {
                return;
            }

            btn.disabled = true;
            const originalText = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

            try {
                let data;

                if (action === 'update-status') {
                    data = await postJson('/admin/api/orders/update-status', payload);
                } else if (action === 'update-payment') {
                    data = await postJson('/api/admin/orders/update-payment', payload);
                } else if (action === 'toggle-active') {
                    data = await postJson('/api/admin/products/toggle-active', payload);
                } else if (action === 'bulk-activate' || action === 'bulk-deactivate') {
                    const pks = getSelectedPks();

                    if (!pks) {
                        alert('Сначала выбери товары');
                        btn.disabled = false;
                        btn.innerHTML = originalText;
                        return;
                    }

                    data = await postForm('/admin/product/action/' + action, { pks: pks });
                } else {
                    console.error('Unknown action:', action);
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                    return;
                }

                if (data.success) {
                    const row = btn.closest('tr');
                    if (row) {
                        row.style.background = '#d4edda';
                    }
                    setTimeout(function() {
                        location.reload();
                    }, 300);
                } else {
                    alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                }
            } catch (err) {
                alert('Ошибка сети: ' + err.message);
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAdminActions);
    } else {
        initAdminActions();
    }
})();
