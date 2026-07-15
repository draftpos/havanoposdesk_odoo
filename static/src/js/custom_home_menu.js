/** @odoo-module **/

import { NavBar } from "@web/webclient/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount, Component, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// 1. Define the Client Action Component
class CustomHomeMenuComponent extends Component {
    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");

        onMounted(() => {
            // Hide the Odoo navbar when the home menu is active
            document.body.classList.add("o_home_menu_active");
        });

        onWillUnmount(() => {
            // Restore the navbar when navigating away
            document.body.classList.remove("o_home_menu_active");
        });
    }

    get apps() {
        const allApps = this.menuService.getApps();
        return allApps.filter(app => app.xmlid !== "havanoposdesk_odoo.menu_custom_home_menu_root");
    }

    onAppClick(ev, app) {
        ev.preventDefault();
        this.menuService.selectMenu(app);
    }
}

CustomHomeMenuComponent.template = xml`
    <div class="custom_home_menu_overlay">
        <div class="custom_home_menu_container">
            <div class="custom_home_menu_grid">
                <t t-foreach="apps" t-as="app" t-key="app.id">
                    <a href="#"
                       class="custom_home_menu_app_card"
                       t-on-click="(ev) => this.onAppClick(ev, app)">
                        <div class="custom_home_menu_app_icon">
                            <t t-if="app.webIconData">
                                <img t-att-src="app.webIconData" alt=""/>
                            </t>
                            <t t-else="">
                                <i class="oi oi-apps"></i>
                            </t>
                        </div>
                        <div class="custom_home_menu_app_name"><t t-esc="app.name"/></div>
                    </a>
                </t>
            </div>
        </div>
    </div>
`;

// Register the Client Action
registry.category("actions").add("custom_home_menu.action", CustomHomeMenuComponent);

// 2. Patch NavBar to replace the apps grid button with a home button
patch(NavBar.prototype, {
    setup() {
        super.setup();
        onMounted(() => {
            this.replaceAppsMenuButton();
        });
    },

    replaceAppsMenuButton() {
        const appsMenuContainer = document.querySelector('.o_navbar_apps_menu');
        if (appsMenuContainer && !appsMenuContainer.classList.contains('custom-replaced')) {
            appsMenuContainer.classList.add('custom-replaced');

            const buttonHtml = '<button class="custom_home_menu_button border-0 bg-transparent" data-hotkey="h" title="Home Menu"><i class="oi oi-apps"></i></button>';
            appsMenuContainer.innerHTML = buttonHtml;

            const customButton = appsMenuContainer.querySelector('.custom_home_menu_button');
            if (customButton) {
                customButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.env.services.action.doAction("havanoposdesk_odoo.action_custom_home_menu", { clearBreadcrumbs: true });
                });
            }
        }
    }
});
