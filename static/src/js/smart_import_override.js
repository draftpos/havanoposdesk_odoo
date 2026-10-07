/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ImportRecords } from "@base_import/import_records/import_records";

patch(ImportRecords.prototype, {
    importRecords() {
        const resModel = this.env?.searchModel?.resModel;
        const context = this.env?.searchModel?.context || {};

        if (resModel === "havanoposdesk.sale") {
            return this.action.doAction({
                name: "Smart Import Sales Invoices",
                type: "ir.actions.act_window",
                res_model: "havanoposdesk.sale.import.wizard",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                context: context,
            });
        }

        if (resModel === "havanoposdesk.purchase") {
            return this.action.doAction({
                name: "Smart Import Purchases",
                type: "ir.actions.act_window",
                res_model: "havanoposdesk.purchase.import.wizard",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                context: context,
            });
        }

        return super.importRecords(...arguments);
    },
});
