(function() {
    'use strict';

    function initAdminActions() {
        document.body.addEventListener('click', async function(e) {
            const btn = e.target.closest('[data-admin-action]');
            if (!btn) return;

            e.preventDefault();
            
            const action = btn.dataset.adminAction;
            const entityId = btn.dataset.entityId;
            const entityType = btn.dataset.entityType;
            const confirmMsg = btn.dataset.confirmMessage;
            const payload = btn.dataset.payload ? JSON.parse(btn.dataset.payload) : {};

            if (confirmMsg && !confirm(confirmMsg)) {
                return;
            }

            btn.disabled = true;
            const originalText = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

            try {
                let endpoint;
                if (action === 'update-status') {
                    endpoint = '/admin/api/orders/update-status';
                } else if (action === 'update-payment') {
                    endpoint = '/api/admin/orders/update-payment';
                } else if (action === 'toggle-active') {
                    endpoint = '/api/admin/products/toggle-active';
                } else {
                    console.error('Unknown action:', action);
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                    return;
                }

                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                const data = await response.json();

                if (data.success) {
                    btn.closest('tr').style.background = '#d4edda';
                    setTimeout(() => location.reload(), 300);
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
