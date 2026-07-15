/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { FormController } from "@web/views/form/form_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { Many2OneField } from "@web/views/fields/many2one/many2one_field";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { Component, xml, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class AccessDeniedModal extends Component {
    static template = xml`
        <Dialog title="props.title" size="'md'">
            <div class="custom-access-denied-modal" style="padding: 20px; text-align: center;">
                <i t-att-class="props.iconClass" t-att-style="'font-size: 50px; margin-bottom: 15px; color: ' + props.iconColor"></i>
                <h3 style="color: #343a40; font-weight: bold; margin-bottom: 10px;" t-esc="props.title"></h3>
                <p style="font-size: 16px; color: #6c757d;" t-esc="props.body" />
                <button class="btn btn-primary" style="margin-top: 20px; padding: 10px 30px; border-radius: 20px;" t-on-click="props.close">Got It</button>
            </div>
            <t t-set-slot="footer">
                <!-- Hide default footer -->
            </t>
        </Dialog>
    `;
    static components = { Dialog };
    static props = ["title", "body", "close", "iconClass", "iconColor"];
}

patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.dialogService = useService("dialog");
        
        onWillStart(async () => {
            try {
                if (this.props.resModel) {
                    console.log("[HAVANO] Checking create access for", this.props.resModel);
                    const canCreate = await this.orm.call(this.props.resModel, "check_access_rights", ["create", false]);
                    console.log("[HAVANO] canCreate result:", canCreate);
                    if (!canCreate) {
                        console.log("[HAVANO] Hiding create buttons!");
                        if (this.props.archInfo && this.props.archInfo.activeActions) {
                            this.props.archInfo.activeActions.create = false;
                        }
                        if (this.activeActions) {
                            this.activeActions.create = false;
                        }
                    }
                }
            } catch (e) {
                console.error("[HAVANO] Error in ListController onWillStart:", e);
            }
        });
    },
    async openRecord(record, params) {
        try {
            if (this.props.resModel) {
                const canRead = await this.orm.call(this.props.resModel, "check_access_rights", ["read", false]);
                if (!canRead) {
                    this.dialogService.add(AccessDeniedModal, {
                        title: "Access Denied",
                        body: "You don't have access to view this record. Please contact your administrator.",
                        iconClass: "fa fa-lock",
                        iconColor: "#dc3545"
                    });
                    return;
                }
                const canEdit = await this.orm.call(this.props.resModel, "check_access_rights", ["write", false]);
                if (!canEdit) {
                    this.dialogService.add(AccessDeniedModal, {
                        title: "Read-Only Access",
                        body: "You have read-only access. You cannot edit this record.",
                        iconClass: "fa fa-eye",
                        iconColor: "#17a2b8"
                    });
                }
            }
        } catch (e) {}
        return super.openRecord(...arguments);
    }
});

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        
        onWillStart(async () => {
            try {
                if (this.props.resModel) {
                    const canCreate = await this.orm.call(this.props.resModel, "check_access_rights", ["create", false]);
                    if (!canCreate && this.props.archInfo && this.props.archInfo.activeActions) {
                        this.props.archInfo.activeActions.create = false;
                    }
                    const canEdit = await this.orm.call(this.props.resModel, "check_access_rights", ["write", false]);
                    if (!canEdit && this.props.archInfo && this.props.archInfo.activeActions) {
                        this.props.archInfo.activeActions.edit = false;
                    }
                }
            } catch (e) {}
        });
    }
});

patch(KanbanController.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.dialogService = useService("dialog");
        
        onWillStart(async () => {
            try {
                if (this.props.resModel) {
                    const canCreate = await this.orm.call(this.props.resModel, "check_access_rights", ["create", false]);
                    if (!canCreate && this.props.archInfo && this.props.archInfo.activeActions) {
                        this.props.archInfo.activeActions.create = false;
                    }
                }
            } catch (e) {}
        });
    },
    async openRecord(record, params) {
        try {
            if (this.props.resModel) {
                const canRead = await this.orm.call(this.props.resModel, "check_access_rights", ["read", false]);
                if (!canRead) {
                    this.dialogService.add(AccessDeniedModal, {
                        title: "Access Denied",
                        body: "You don't have access to view this record. Please contact your administrator.",
                        iconClass: "fa fa-lock",
                        iconColor: "#dc3545"
                    });
                    return;
                }
                const canEdit = await this.orm.call(this.props.resModel, "check_access_rights", ["write", false]);
                if (!canEdit) {
                    this.dialogService.add(AccessDeniedModal, {
                        title: "Read-Only Access",
                        body: "You have read-only access. You cannot edit this record.",
                        iconClass: "fa fa-eye",
                        iconColor: "#17a2b8"
                    });
                }
            }
        } catch (e) {}
        return super.openRecord(...arguments);
    }
});

patch(Many2OneField.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        
        onWillStart(async () => {
            try {
                const relation = this.props.relation || (this.props.record && this.props.record.fields[this.props.name].relation);
                if (relation) {
                    const canCreate = await this.orm.call(relation, "check_access_rights", ["create", false]);
                    if (!canCreate) {
                        this.havanoHideCreate = true;
                    }
                }
            } catch (e) {}
        });
    },
    get m2oProps() {
        const props = super.m2oProps;
        if (this.havanoHideCreate) {
            props.canCreate = false;
            props.canCreateEdit = false;
            props.canQuickCreate = false;
        }
        return props;
    }
});
