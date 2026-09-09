/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { Many2OneField } from "@web/views/fields/many2one/many2one_field";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

export class VariantSelectorDialog extends Component {
    static template = "havanoposdesk_odoo.VariantSelectorDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        productName: { type: String, optional: true },
        variants: Array,
        onSelectVariant: Function,
    };

    setup() {
        this.state = useState({
            selectedVariantId: this.props.variants.length > 0 ? this.props.variants[0].id : null,
            searchTerm: "",
        });
    }

    get filteredVariants() {
        if (!this.state.searchTerm.trim()) {
            return this.props.variants;
        }
        const term = this.state.searchTerm.toLowerCase().trim();
        return this.props.variants.filter((v) =>
            v.name.toLowerCase().includes(term)
        );
    }

    selectRow(variant) {
        this.state.selectedVariantId = variant.id;
    }

    async confirm() {
        const selected = this.props.variants.find(
            (v) => v.id === this.state.selectedVariantId
        );
        if (selected) {
            await this.props.onSelectVariant(selected);
            this.props.close();
        }
    }

    async chooseDirectly(variant) {
        this.state.selectedVariantId = variant.id;
        await this.props.onSelectVariant(variant);
        this.props.close();
    }
}

// ─── Automatically Prompt Variant Selector When Product is Chosen ─────────────
patch(Many2OneField.prototype, {
    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this.orm = useService("orm");
    },

    get m2oProps() {
        const props = super.m2oProps;
        const record = this.props.record;
        const fieldName = this.props.name;
        const relation = record?.fields?.[fieldName]?.relation;

        if (relation === "havanoposdesk.product" && record?.fields && "variant_id" in record.fields) {
            const originalUpdate = props.update;
            return {
                ...props,
                update: async (value, options = {}) => {
                    await originalUpdate(value, options);
                    const prodId = Array.isArray(value) ? (value[0]?.id || value[0]) : (value?.id || value);
                    if (prodId && typeof prodId === "number") {
                        await this.openVariantSelectorIfAvailable(prodId);
                    }
                },
            };
        }
        return props;
    },

    async openVariantSelectorIfAvailable(productId) {
        try {
            const variants = await this.orm.search_read(
                "havanoposdesk.product.variant",
                [["product_id", "=", productId]],
                ["id", "name", "cost_price", "selling_price", "on_hand_qty"]
            );

            if (variants && variants.length > 0) {
                const prodData = this.props.record.data[this.props.name];
                let productName = "";
                if (prodData) {
                    if (typeof prodData === "object" && !Array.isArray(prodData)) {
                        productName = prodData.display_name || "";
                    } else if (Array.isArray(prodData)) {
                        productName = prodData[1] || "";
                    }
                }

                this.dialog.add(VariantSelectorDialog, {
                    productName: productName,
                    variants: variants,
                    onSelectVariant: async (variant) => {
                        await this.props.record.update({
                            variant_id: { id: variant.id, display_name: variant.name },
                        });
                    },
                });
            }
        } catch (err) {
            console.error("Failed to check or open variant selector modal:", err);
        }
    },
});
