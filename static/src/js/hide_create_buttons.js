/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { FormController } from "@web/views/form/form_controller";
import { BooleanToggleField } from "@web/views/fields/boolean_toggle/boolean_toggle_field";
import { patch } from "@web/core/utils/patch";
import { onWillStart, onMounted, onWillUnmount } from "@odoo/owl";

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
function showAccessDeniedDialog(featureName, action = 'view') {
    let readableMsg;
    if (action === 'create') {
        readableMsg = featureName
            ? `You have <strong>Read-Only</strong> access to <strong>${featureName}</strong>.<br>You cannot create new records here.<br><br>Please contact your administrator if you need full access.`
            : `You don't have permission to create records here.<br>Please contact your administrator if you need access.`;
    } else if (action === 'edit') {
        readableMsg = featureName
            ? `You have <strong>Read-Only</strong> access to <strong>${featureName}</strong>.<br>You cannot edit records here.<br><br>Please contact your administrator if you need full access.`
            : `You don't have permission to edit records here.<br>Please contact your administrator if you need access.`;
    } else if (action === 'delete') {
        readableMsg = featureName
            ? `You have <strong>Read-Only</strong> access to <strong>${featureName}</strong>.<br>You cannot delete records here.<br><br>Please contact your administrator if you need full access.`
            : `You don't have permission to delete records here.<br>Please contact your administrator if you need access.`;
    } else {
        readableMsg = featureName
            ? `You don't have permission to open <strong>${featureName}</strong> records.<br>Please contact your administrator if you need access.`
            : `You don't have permission to view this record.<br>Please contact your administrator if you need access.`;
    }

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
const _accessCache = {};

async function checkModelAccess(rpc, model) {
    if (_accessCache[model] !== undefined) {
        return _accessCache[model];
    }
    try {
        const result = await rpc("/havano/check_access", { model: model });
        const access = {
            canCreate: result.canCreate !== false,
            canViewDetail: result.canViewDetail !== false,
            canEdit: result.canEdit !== false,
            canDelete: result.canDelete !== false,
        };
        _accessCache[model] = access;
        return access;
    } catch {
        return { canCreate: true, canViewDetail: true, canEdit: true, canDelete: true };
    }
}

function getModelLabel(model) {
    if (!model) return '';
    const parts = model.split('.');
    return parts[parts.length - 1]
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * Aggressively hide buttons in the DOM using MutationObserver.
 * Returns the observer so it can be disconnected on unmount.
 */
function startButtonHider(access) {
    const hideButtons = () => {
        // Hide "New" / create buttons
        if (!access.canCreate) {
            document.body.querySelectorAll(
                '.o_list_button_add, .o_kanban_button_new, button[data-hotkey="c"], .o_control_panel_actions .btn-primary'
            ).forEach(btn => {
                const txt = btn.textContent.trim();
                if (txt === 'New' || btn.dataset.hotkey === 'c' || txt === 'New' || btn.classList.contains('o_list_button_add')) {
                    btn.style.setProperty('display', 'none', 'important');
                }
            });
        }

        // Hide Edit / Save buttons in form view
        if (!access.canEdit) {
            document.body.querySelectorAll(
                '.o_form_button_edit, .o_form_button_save, button.o_form_button_edit'
            ).forEach(btn => {
                btn.style.setProperty('display', 'none', 'important');
            });
        }

        // Hide Delete (Action menu > Delete option)
        if (!access.canDelete) {
            document.body.querySelectorAll(
                '.o_cp_action_menus .dropdown-item[data-section="other"]'
            ).forEach(item => {
                if (item.textContent.trim() === 'Delete') {
                    item.style.setProperty('display', 'none', 'important');
                }
            });
        }
    };

    hideButtons();
    const observer = new MutationObserver(hideButtons);
    observer.observe(document.body, { childList: true, subtree: true });
    return observer;
}

// ─── List Controller Patch ────────────────────────────────────────────────────
patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        this.__havanoAccess = { canCreate: true, canViewDetail: true, canEdit: true, canDelete: true };

        onWillStart(async () => {
            const rpc = this.env.services.rpc;
            this.__havanoAccess = await checkModelAccess(rpc, this.props.resModel);

            if (!this.__havanoAccess.canCreate) {
                // Mutate activeActions to prevent the "New" button from rendering
                if (this.props.archInfo && this.props.archInfo.activeActions) {
                    this.props.archInfo.activeActions.create = false;
                }
                if (this.activeActions) {
                    this.activeActions.create = false;
                }
            }

            if (!this.__havanoAccess.canDelete) {
                if (this.props.archInfo && this.props.archInfo.activeActions) {
                    this.props.archInfo.activeActions.delete = false;
                }
            }
        });

        onMounted(() => {
            const needsHiding = !this.__havanoAccess.canCreate || !this.__havanoAccess.canEdit || !this.__havanoAccess.canDelete;
            if (needsHiding) {
                this.__havanoObserver = startButtonHider(this.__havanoAccess);
            }
        });

        onWillUnmount(() => {
            if (this.__havanoObserver) {
                this.__havanoObserver.disconnect();
                this.__havanoObserver = null;
            }
        });
    },

    // Intercept row clicks
    async openRecord(record, { force, newWindow } = { force: false }) {
        if (!this.__havanoAccess.canViewDetail) {
            const label = getModelLabel(record.resModel || this.props.resModel);
            showAccessDeniedDialog(label, 'view');
            return;
        }
        return super.openRecord(record, { force, newWindow });
    },

    // Fallback: intercept createRecord if JS button hide fails
    async createRecord() {
        if (!this.__havanoAccess.canCreate) {
            const label = getModelLabel(this.props.resModel);
            showAccessDeniedDialog(label, 'create');
            return;
        }
        return super.createRecord();
    }
});

// ─── Kanban Controller Patch ──────────────────────────────────────────────────
patch(KanbanController.prototype, {
    setup() {
        super.setup(...arguments);
        this.__havanoAccess = { canCreate: true, canViewDetail: true, canEdit: true, canDelete: true };

        onWillStart(async () => {
            const rpc = this.env.services.rpc;
            this.__havanoAccess = await checkModelAccess(rpc, this.props.resModel);

            if (!this.__havanoAccess.canCreate) {
                if (this.props.archInfo && this.props.archInfo.activeActions) {
                    this.props.archInfo.activeActions.create = false;
                }
                if (this.activeActions) {
                    this.activeActions.create = false;
                }
            }
        });

        onMounted(() => {
            const needsHiding = !this.__havanoAccess.canCreate || !this.__havanoAccess.canEdit || !this.__havanoAccess.canDelete;
            if (needsHiding) {
                this.__havanoObserver = startButtonHider(this.__havanoAccess);
            }
        });

        onWillUnmount(() => {
            if (this.__havanoObserver) {
                this.__havanoObserver.disconnect();
                this.__havanoObserver = null;
            }
        });
    },

    async openRecord(record, { newWindow } = {}) {
        if (!this.__havanoAccess.canViewDetail) {
            const label = getModelLabel(this.props.resModel);
            showAccessDeniedDialog(label, 'view');
            return;
        }
        return super.openRecord(record, { newWindow });
    },

    async createRecord() {
        if (!this.__havanoAccess.canCreate) {
            const label = getModelLabel(this.props.resModel);
            showAccessDeniedDialog(label, 'create');
            return;
        }
        return super.createRecord();
    }
});

// ─── Form Controller Patch ────────────────────────────────────────────────────
// Ensures the form view opened from a list also respects read-only access
patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.__havanoAccess = { canCreate: true, canViewDetail: true, canEdit: true, canDelete: true };

        onWillStart(async () => {
            const rpc = this.env.services.rpc;
            this.__havanoAccess = await checkModelAccess(rpc, this.props.resModel);

            if (!this.__havanoAccess.canCreate && this.props.archInfo && this.props.archInfo.activeActions) {
                this.props.archInfo.activeActions.create = false;
            }
            if (!this.__havanoAccess.canEdit && this.props.archInfo && this.props.archInfo.activeActions) {
                this.props.archInfo.activeActions.edit = false;
            }
            if (!this.__havanoAccess.canDelete && this.props.archInfo && this.props.archInfo.activeActions) {
                this.props.archInfo.activeActions.delete = false;
            }
        });

        onMounted(() => {
            const needsHiding = !this.__havanoAccess.canCreate || !this.__havanoAccess.canEdit || !this.__havanoAccess.canDelete;
            if (needsHiding) {
                this.__havanoObserver = startButtonHider(this.__havanoAccess);
            }
        });

        onWillUnmount(() => {
            if (this.__havanoObserver) {
                this.__havanoObserver.disconnect();
                this.__havanoObserver = null;
            }
        });
    }
});
