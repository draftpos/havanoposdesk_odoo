/** @odoo-module **/
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { registry } from "@web/core/registry";
import { useEffect } from "@odoo/owl";

function getStoreId(storeVal) {
    if (!storeVal) return null;
    if (Array.isArray(storeVal)) {
        return storeVal[0] || null;
    }
    if (typeof storeVal === "object") {
        return storeVal.resId || storeVal.id || null;
    }
    if (typeof storeVal === "number") {
        return storeVal;
    }
    return null;
}

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
                const fromStoreId = getStoreId(record.data.from_store_id);
                const toStoreId = getStoreId(record.data.to_store_id);
                return [fromStoreId, toStoreId];
            }
        );
    }

    _checkSameStore() {
        const record = this.model.root;
        if (!record) return;

        const fromStoreId = getStoreId(record.data.from_store_id);
        const toStoreId = getStoreId(record.data.to_store_id);

        const warning = document.getElementById("havano_same_store_warning");
        if (!warning) return;

        if (fromStoreId && toStoreId && fromStoreId === toStoreId) {
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
