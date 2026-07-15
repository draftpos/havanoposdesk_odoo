/** @odoo-module **/

/**
 * Havano Access Error Handler
 * ----------------------------
 * Intercepts Odoo's global error notification service.
 * When the server raises an AccessError (e.g., "Permission Denied" from
 * user_rights.py), instead of showing the default Odoo red error dialog,
 * we display our custom branded "Access Restricted" modal.
 */

console.log("🛡️ HAVANO: access_error_handler.js loaded");

// ─── Shared Modal Renderer ─────────────────────────────────────────────────────
function showHavanoAccessDeniedModal(message) {
    // Remove any existing modal first to avoid stacking
    document.querySelectorAll('.havano-access-overlay').forEach(el => el.remove());

    let featureName = '';
    const match = message && message.match(/access to '([^']+)'/i);
    if (match) {
        featureName = match[1];
    }

    const readableMsg = featureName
        ? `You have <strong>Read-Only</strong> access to <strong>${featureName}</strong>.<br>You cannot create, modify, or delete records here.<br><br>Please contact your administrator if you need full access.`
        : `You don't have permission to perform this action.<br>Please contact your administrator if you need access.`;

    const overlay = document.createElement('div');
    overlay.className = 'havano-access-overlay';
    overlay.innerHTML = `
        <div class="havano-access-dialog">
            <div class="havano-access-dialog-icon">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 2C9.24 2 7 4.24 7 7v2H5c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V11c0-1.1-.9-2-2-2h-2V7c0-2.76-2.24-5-5-5zm0 13c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3-11v2H9V7c0-1.66 1.34-3 3-3s3 1.34 3 3z" fill="currentColor"/>
                </svg>
            </div>
            <h3 class="havano-access-dialog-title">Access Restricted</h3>
            <p class="havano-access-dialog-message">${readableMsg}</p>
            <button class="havano-access-dialog-btn" id="havano-dialog-close">Got it</button>
        </div>
    `;

    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    overlay.querySelector('#havano-dialog-close').addEventListener('click', () => overlay.remove());
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('visible'));
}

// ─── Global unhandledrejection fallback ───────────────────────────────────────
// Belt-and-suspenders: if a rejected promise with a permission error bubbles
// all the way up to the window without being caught by the ErrorHandler patch
// above, we catch it here.
window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    if (!reason) return;

    const msg = reason?.data?.message || reason?.message || String(reason);
    if (
        msg.includes('Permission Denied') ||
        msg.includes('AccessError') ||
        msg.includes('Read-Only access') ||
        msg.includes('No User Rights Profile')
    ) {
        // We do NOT preventDefault so Odoo's error handler doesn't get completely disabled for other things,
        // but we intercept to show our custom dialog.
        // Actually, preventing default stops the browser from logging it, and stops Odoo's unhandledrejection listener if we're first.
        event.stopImmediatePropagation(); // Try to stop Odoo from showing its own dialog if we caught it first
        event.preventDefault(); 
        
        // Remove Odoo's default error dialog if it appeared
        setTimeout(() => {
            document.querySelectorAll('.o_error_dialog').forEach(el => el.remove());
            document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
            document.body.classList.remove('modal-open');
        }, 100);

        showHavanoAccessDeniedModal(msg);
    }
});
