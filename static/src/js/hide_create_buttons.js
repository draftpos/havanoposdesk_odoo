/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { BooleanToggleField } from "@web/views/fields/boolean_toggle/boolean_toggle_field";
import { patch } from "@web/core/utils/patch";
import { onWillStart, onMounted } from "@odoo/owl";

// ─── Havano Models Allowlist ───────────────────────────────────────────────────
console.log("🔥 HAVANO JS LOADED: hide_create_buttons.js");

// ─── Boolean Toggle Patch for Mutual Exclusivity ──────────────────────────────
patch(BooleanToggleField.prototype, {
    async onChange(newValue) {
        await super.onChange(newValue);
        if (this.props.record.resModel === 'havanoposdesk.backoffice.permission') {
            if (this.props.name === 'is_full_access') {
                await this.props.record.update({ is_read_only: !newValue });
            } else if (this.props.name === 'is_read_only') {
                await this.props.record.update({ is_full_access: !newValue });
            }
        }
    }
});

// ─── Custom Access Denied Dialog ──────────────────────────────────────────────
function showAccessDeniedDialog(featureName) {
    const readableMsg = featureName
        ? `You don't have permission to open <strong>${featureName}</strong> records.<br>Please contact your administrator if you need access.`
        : `You don't have permission to view this record.<br>Please contact your administrator if you need access.`;

    document.querySelectorAll('.havano-access-overlay').forEach(el => el.remove());

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

// ─── Helpers ──────────────────────────────────────────────────────────────────
async function checkModelAccess(rpc, model) {
    try {
        const result = await rpc("/havano/check_access", { model: model });
        return { canCreate: result.canCreate, canViewDetail: result.canViewDetail };
    } catch {
        return { canCreate: true, canViewDetail: true };
    }
}

function hideNewButtonInDom(rootEl) {
    if (!rootEl) return;
    const hide = () => {
        rootEl.querySelectorAll('.o_list_button_add, button[data-hotkey="c"]').forEach(btn => {
            if (btn.textContent.trim() === 'New' || btn.dataset.hotkey === 'c') {
                btn.style.setProperty('display', 'none', 'important');
            }
        });
    };
    hide();
    new MutationObserver(hide).observe(rootEl, { childList: true, subtree: true });
}

// ─── List Controller Patch ────────────────────────────────────────────────────
patch(ListController.prototype, {
        setup() {
            super.setup(...arguments);
            this.__havanoAccess = { canCreate: true, canViewDetail: true };

            onWillStart(async () => {
                const rpc = this.env.services.rpc;
                this.__havanoAccess = await checkModelAccess(rpc, this.props.resModel);
                
                if (!this.__havanoAccess.canCreate) {
                    this.activeActions = Object.assign({}, this.activeActions, { create: false });
                }
            });

        onMounted(() => {
            if (!this.__havanoAccess.canCreate && this.rootRef?.el) {
                hideNewButtonInDom(this.rootRef.el);
            }
        });
    },

    // Intercept row clicks ONLY — list view loading is unaffected
    async openRecord(record, { force, newWindow } = { force: false }) {
        if (!this.__havanoAccess.canViewDetail) {
            const modelLabel = record.resModel || this.props.resModel || '';
            const parts = modelLabel.split('.');
            const label = parts[parts.length - 1]
                .replace(/_/g, ' ')
                .replace(/\b\w/g, c => c.toUpperCase());
            showAccessDeniedDialog(label);
            return; // Block the form view from opening
        }
        return super.openRecord(record, { force, newWindow });
    }
});

// ─── Kanban Controller Patch ──────────────────────────────────────────────────
patch(KanbanController.prototype, {
        setup() {
            super.setup(...arguments);
            this.__havanoAccess = { canCreate: true, canViewDetail: true };

            onWillStart(async () => {
                const rpc = this.env.services.rpc;
                this.__havanoAccess = await checkModelAccess(rpc, this.props.resModel);
                
                if (!this.__havanoAccess.canCreate) {
                    this.activeActions = Object.assign({}, this.activeActions, { create: false });
                }
            });

        onMounted(() => {
            if (!this.__havanoAccess.canCreate) {
                const root = document.querySelector('.o_kanban_view');
                if (root) hideNewButtonInDom(root);
            }
        });
    },

    async openRecord(record, { newWindow } = {}) {
        if (!this.__havanoAccess.canViewDetail) {
            const modelLabel = this.props.resModel || '';
            const parts = modelLabel.split('.');
            const label = parts[parts.length - 1]
                .replace(/_/g, ' ')
                .replace(/\b\w/g, c => c.toUpperCase());
            showAccessDeniedDialog(label);
            return;
        }
        return super.openRecord(record, { newWindow });
    }
});
