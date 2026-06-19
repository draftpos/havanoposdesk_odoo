/** @odoo-module **/

import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import "@web/webclient/user_menu/user_menu_items";

const userMenuRegistry = registry.category("user_menuitems");

const itemsToRemove = [
    "support",
    "shortcuts",
    "preferences",
    "odoo_account",
    "install_pwa",
    "separator"
];

function removeUnwantedItems() {
    if (!user.isAdmin) {
        itemsToRemove.forEach((item) => {
            if (userMenuRegistry.contains(item)) {
                userMenuRegistry.remove(item);
            }
        });
    }
}

// Remove items if they are already registered
removeUnwantedItems();

// Listen for items added later and remove them
userMenuRegistry.addEventListener("UPDATE", (ev) => {
    if (ev.detail.operation === "add" && !user.isAdmin && itemsToRemove.includes(ev.detail.key)) {
        userMenuRegistry.remove(ev.detail.key);
    }
});
