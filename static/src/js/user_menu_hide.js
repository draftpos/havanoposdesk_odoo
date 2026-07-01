/** @odoo-module **/

import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import "@web/webclient/user_menu/user_menu_items";

const userMenuRegistry = registry.category("user_menuitems");

const itemsToRemove = [
    "documentation",
    "support",
    "shortcuts",
    "odoo_account",
    "install_pwa",
    "separator"
];

function removeUnwantedItems() {
    itemsToRemove.forEach((item) => {
        if (userMenuRegistry.contains(item)) {
            userMenuRegistry.remove(item);
        }
    });
}

// Remove items if they are already registered
removeUnwantedItems();

// Listen for items added later and remove them
userMenuRegistry.addEventListener("UPDATE", (ev) => {
    if (ev.detail.operation === "add" && itemsToRemove.includes(ev.detail.key)) {
        userMenuRegistry.remove(ev.detail.key);
    }
});
