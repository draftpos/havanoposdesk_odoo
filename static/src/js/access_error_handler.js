/** @odoo-module **/

/**
 * Havano Access Error Handler
 * ----------------------------
 * Intercepts Odoo's global error notification service.
 * When the server raises an AccessError (e.g., "Permission Denied" from
 * user_rights.py), instead of showing the default Odoo red error dialog,
 * we display our custom branded "Access Restricted" modal.
 *
 * This acts as the FALLBACK SAFETY NET — if the JS button-hiding fails for
 * any reason and the user somehow triggers a create/write/unlink, the server
 * will reject it and this handler will intercept the error and show the
 * correct UI response.
 */

import { patch } from "@web/core/utils/patch";
import { ErrorHandler } from "@web/core/errors/error_handler";
import { RPCError } from "@web/core/network/rpc";

console.log("🛡️ HAVANO: access_error_handler.js loaded");

// ─── Shared Modal Renderer ─────────────────────────────────────────────────────
// This function is self-contained so it works even if the other JS file hasn't
// loaded (defence-in-depth).
function showHavanoAccessDeniedModal(message) {
    // Remove any existing modal first to avoid stacking
    document.querySelectorAll('.havano-access-overlay').forEach(el => el.remove());

    // Extract feature name from the error message if present
    // Our Python raises: "Permission Denied: You have Read-Only access to 'Sales Invoices'."
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

// ─── Patch the ErrorHandler to intercept AccessError ─────────────────────────
patch(ErrorHandler.prototype, {
    /**
     * Odoo calls handleError() when an unhandled error propagates up from an
     * async OWL component or a failed RPC. We check here if it is one of our
     * Permission Denied errors and, if so, render our modal and mark the error
     * as handled so Odoo's default crash dialog never appears.
     */
    handleError(error, component, info) {
        // Walk through the error cause chain to find an RPC error
        let cause = error;
        while (cause) {
            if (cause instanceof RPCError || (cause && cause.name === 'RPC_ERROR')) {
                const serverMsg = cause.data?.message || cause.message || '';
                if (
                    serverMsg.includes('Permission Denied') ||
                    serverMsg.includes('permission denied') ||
                    serverMsg.includes('AccessError') ||
                    serverMsg.includes('Read-Only access') ||
                    serverMsg.includes('No User Rights Profile')
                ) {
                    showHavanoAccessDeniedModal(serverMsg);
                    // Return true to mark error as "handled" — suppresses Odoo's default crash
                    return true;
                }
            }
            cause = cause.cause || null;
        }
        // Not a permission error — let Odoo handle it normally
        return super.handleError(error, component, info);
    }
});

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
        event.preventDefault(); // Suppress default browser error
        showHavanoAccessDeniedModal(msg);
    }
});
