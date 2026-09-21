/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { FormController } from "@web/views/form/form_controller";
import { BooleanToggleField } from "@web/views/fields/boolean_toggle/boolean_toggle_field";
import { patch } from "@web/core/utils/patch";
import { onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { session } from "@web/session";

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

// ─── High Performance Cached Access Checker ──────────────────────────────────
const _accessCache = {};
const FULL_ACCESS = { canCreate: true, canViewDetail: true, canEdit: true, canDelete: true };

async function checkModelAccess(rpc, model) {
    if (!model) return FULL_ACCESS;
    if (_accessCache[model] !== undefined) {
        return _accessCache[model];
    }
    // Admin / Super Admin bypass without network roundtrips
    if (session.is_admin || session.uid === 1 || session.havano_role === 'super_admin') {
        _accessCache[model] = FULL_ACCESS;
        return FULL_ACCESS;
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
        return FULL_ACCESS;
    }
}

function getModelLabel(model) {
    if (!model) return '';
    const parts = model.split('.');
    return parts[parts.length - 1]
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase());
}

// ─── List Controller Patch ────────────────────────────────────────────────────
patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        this.__havanoAccess = FULL_ACCESS;

        onWillStart(async () => {
            const rpc = this.env.services.rpc;
            const access = await checkModelAccess(rpc, this.props.resModel);
            this.__havanoAccess = access;
            if (this.props.archInfo && this.props.archInfo.activeActions) {
                if (!access.canCreate) this.props.archInfo.activeActions.create = false;
                if (!access.canEdit) this.props.archInfo.activeActions.edit = false;
                if (!access.canDelete) this.props.archInfo.activeActions.delete = false;
            }
            if (this.activeActions) {
                if (!access.canCreate) this.activeActions.create = false;
                if (!access.canEdit) this.activeActions.edit = false;
                if (!access.canDelete) this.activeActions.delete = false;
            }
        });

        onMounted(() => {
            if (!this.__havanoAccess.canCreate) document.body.classList.add('havano-no-create');
            if (!this.__havanoAccess.canEdit) document.body.classList.add('havano-no-edit');
            if (!this.__havanoAccess.canDelete) document.body.classList.add('havano-no-delete');
        });

        onWillUnmount(() => {
            document.body.classList.remove('havano-no-create', 'havano-no-edit', 'havano-no-delete');
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

    // Fallback: intercept createRecord if triggered
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
        this.__havanoAccess = FULL_ACCESS;

        onWillStart(async () => {
            const rpc = this.env.services.rpc;
            const access = await checkModelAccess(rpc, this.props.resModel);
            this.__havanoAccess = access;
            if (this.props.archInfo && this.props.archInfo.activeActions) {
                if (!access.canCreate) this.props.archInfo.activeActions.create = false;
                if (!access.canDelete) this.props.archInfo.activeActions.delete = false;
            }
            if (this.activeActions) {
                if (!access.canCreate) this.activeActions.create = false;
                if (!access.canDelete) this.activeActions.delete = false;
            }
        });

        onMounted(() => {
            if (!this.__havanoAccess.canCreate) document.body.classList.add('havano-no-create');
            if (!this.__havanoAccess.canDelete) document.body.classList.add('havano-no-delete');
        });

        onWillUnmount(() => {
            document.body.classList.remove('havano-no-create', 'havano-no-delete');
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
patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.__havanoAccess = FULL_ACCESS;

        onWillStart(async () => {
            const rpc = this.env.services.rpc;
            const access = await checkModelAccess(rpc, this.props.resModel);
            this.__havanoAccess = access;
            if (this.props.archInfo && this.props.archInfo.activeActions) {
                if (!access.canCreate) this.props.archInfo.activeActions.create = false;
                if (!access.canEdit) this.props.archInfo.activeActions.edit = false;
                if (!access.canDelete) this.props.archInfo.activeActions.delete = false;
            }
        });

        onMounted(() => {
            if (!this.__havanoAccess.canCreate) document.body.classList.add('havano-no-create');
            if (!this.__havanoAccess.canEdit) document.body.classList.add('havano-no-edit');
            if (!this.__havanoAccess.canDelete) document.body.classList.add('havano-no-delete');
        });

        onWillUnmount(() => {
            document.body.classList.remove('havano-no-create', 'havano-no-edit', 'havano-no-delete');
        });
    }
});
