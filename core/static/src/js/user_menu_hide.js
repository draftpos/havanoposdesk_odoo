/** @odoo-module **/

import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import "@web/webclient/user_menu/user_menu_items";

const userMenuRegistry = registry.category("user_menuitems");

// If the user is NOT an admin, remove standard profile dropdown items.
if (!user.isAdmin) {
    const itemsToRemove = [
        "support",
        "shortcuts",
        "preferences",
        "odoo_account",
        "install_pwa",
        "separator"
    ];
    
    itemsToRemove.forEach((item) => {
        if (userMenuRegistry.contains(item)) {
            userMenuRegistry.remove(item);
        }
    });
}
