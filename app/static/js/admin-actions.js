(function() {
    'use strict';

    function getSelectedPks() {
        const selected = [];

        document.querySelectorAll('input[name="pks"]:checked').forEach(function(el) {
            if (el.value) {
                selected.push(el.value);
            }
        });

        return selected;
    }

    function setLoadingState(el, isLoading) {
        if (!el) return;

        if (isLoading) {
            el.dataset.originalText = el.innerHTML;
            el.classList.add('disabled');
            el.setAttribute('aria-disabled', 'true');
            el.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        } else {
            if (el.dataset.originalText) {
                el.innerHTML = el.dataset.originalText;
            }
            el.classList.remove('disabled');
            el.removeAttribute('aria-disabled');
        }
    }

    async function postJson(endpoint, payload) {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const contentType = response.headers.get('content-type') || '';

        if (contentType.includes('application/json')) {
            return await response.json();
        }

        if (response.ok || response.redirected) {
            return { success: true };
        }

        return { success: false, error: 'Неожиданный ответ сервера' };
    }

    async function postBulkAction(endpoint, pks) {
        const url = endpoint + '?pks=' + encodeURIComponent(pks.join(','));

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        const contentType = response.headers.get('content-type') || '';

        if (contentType.includes('application/json')) {
            return await response.json();
        }

        if (response.ok || response.redirected) {
            return { success: true };
        }

        return { success: false, error: 'Неожиданный ответ сервера' };
    }

    async function handleDataAdminAction(btn) {
        const action = btn.dataset.adminAction;
        const confirmMsg = btn.dataset.confirmMessage;
        const payload = btn.dataset.payload ? JSON.parse(btn.dataset.payload) : {};

        if (confirmMsg && !confirm(confirmMsg)) {
            return;
        }

        setLoadingState(btn, true);

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
                setLoadingState(btn, false);
                return;
            }

            const data = await postJson(endpoint, payload);

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
                setLoadingState(btn, false);
            }
        } catch (err) {
            alert('Ошибка сети: ' + err.message);
            setLoadingState(btn, false);
        }
    }

    async function handleBulkAction(link, endpoint, confirmMessage) {
        const pks = getSelectedPks();

        if (!pks.length) {
            alert('Сначала выбери товары');
            return;
        }

        if (confirmMessage && !confirm(confirmMessage)) {
            return;
        }

        setLoadingState(link, true);

        try {
            const data = await postBulkAction(endpoint, pks);

            if (data.success) {
                setTimeout(function() {
                    location.reload();
                }, 300);
            } else {
                alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
                setLoadingState(link, false);
            }
        } catch (err) {
            alert('Ошибка сети: ' + err.message);
            setLoadingState(link, false);
        }
    }

    function initAdminActions() {
        document.body.addEventListener('click', async function(e) {
            const btn = e.target.closest('[data-admin-action]');
            if (btn) {
                e.preventDefault();
                await handleDataAdminAction(btn);
                return;
            }

            const bulkDeactivateLink = e.target.closest('#action-customconfirm-bulk-deactivate');
            if (bulkDeactivateLink) {
                e.preventDefault();
                await handleBulkAction(
                    bulkDeactivateLink,
                    '/admin/product/action/bulk_deactivate',
                    'Деактивировать выбранные товары?'
                );
                return;
            }

            const bulkActivateLink = e.target.closest('#action-customconfirm-bulk-activate');
            if (bulkActivateLink) {
                e.preventDefault();
                await handleBulkAction(
                    bulkActivateLink,
                    '/admin/product/action/bulk_activate',
                    'Активировать выбранные товары?'
                );
                return;
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAdminActions);
    } else {
        initAdminActions();
    }
})();
