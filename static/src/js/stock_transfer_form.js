/** @odoo-module **/
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { registry } from "@web/core/registry";
import { useEffect } from "@odoo/owl";

class HavanoStockTransferFormController extends FormController {
    setup() {
        super.setup();
        useEffect(
            () => {
                this._checkSameStore();
            },
            () => {
                const record = this.model.root;
                if (!record) return [];
                const fromStore = record.data.from_store_id;
                const toStore = record.data.to_store_id;
                return [
                    fromStore ? fromStore[0] : null,
                    toStore ? toStore[0] : null,
                ];
            }
        );
    }

    _checkSameStore() {
        const record = this.model.root;
        if (!record) return;

        const fromStore = record.data.from_store_id;
        const toStore = record.data.to_store_id;

        const warning = document.getElementById("havano_same_store_warning");
        if (!warning) return;

        if (fromStore && toStore && fromStore[0] === toStore[0]) {
            warning.classList.remove("d-none");
            warning.style.animation = "none";
            warning.offsetHeight; // trigger reflow
            warning.style.animation = "havano-fade-in 0.3s ease";
        } else {
            warning.classList.add("d-none");
        }
    }
}

registry.category("views").add("havano_stock_transfer_form", {
    ...formView,
    Controller: HavanoStockTransferFormController,
});
