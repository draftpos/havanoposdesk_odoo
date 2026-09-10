/** @odoo-module **/

import { NavBar } from "@web/webclient/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount, Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

export class CustomHomeMenuComponent extends Component {
    static template = "havanoposdesk_odoo.CustomHomeMenu";
    static props = { "*": true };

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");

        onMounted(() => {
            document.body.classList.add("o_home_menu_active");
        });

        onWillUnmount(() => {
            document.body.classList.remove("o_home_menu_active");
        });
    }

    get apps() {
        const allApps = this.menuService.getApps();
        let apps = allApps.filter((app) => app.xmlid !== "havanoposdesk_odoo.menu_custom_home_menu_root");
        if (!session.biz_enable_payroll) {
            apps = apps.filter((app) => app.xmlid !== "havanoposdesk_odoo.menu_payroll_root");
        }
        return apps;
    }

    onAppClick(ev, app) {
        ev.preventDefault();
        this.menuService.selectMenu(app);
    }
}

registry.category("actions").add("custom_home_menu.action", CustomHomeMenuComponent);

patch(NavBar.prototype, {
    setup() {
        super.setup();
        onMounted(() => {
            this.replaceAppsMenuButton();
        });
    },

    replaceAppsMenuButton() {
        const appsMenuContainer = document.querySelector(".o_navbar_apps_menu");
        if (!appsMenuContainer || appsMenuContainer.classList.contains("custom-replaced")) {
            return;
        }
        appsMenuContainer.classList.add("custom-replaced");

        const buttonHtml =
            '<button class="custom_home_menu_button border-0 bg-transparent" data-hotkey="h" title="Home Menu"><i class="oi oi-apps"></i></button>';
        appsMenuContainer.innerHTML = buttonHtml;

        const customButton = appsMenuContainer.querySelector(".custom_home_menu_button");
        if (customButton) {
            customButton.addEventListener("click", (e) => {
                e.preventDefault();
                this.env.services.action.doAction("havanoposdesk_odoo.action_custom_home_menu", {
                    clearBreadcrumbs: true,
                });
            });
        }
    },
});
