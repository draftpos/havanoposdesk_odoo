/** @odoo-module **/

import { NavBar } from "@web/webclient/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

console.log("Havano Custom Home Menu JS is loading!");

// Patch the NavBar component
patch(NavBar.prototype, {
    setup() {
        super.setup();

        // Initialize custom home menu state
        if (!this.state.isCustomHomeMenuOpen) {
            this.state.isCustomHomeMenuOpen = false;
        }

        // Mount the overlay and replace button after component is mounted
        onMounted(() => {
            console.log("NavBar Mounted - running replaceAppsMenuButton");
            this.renderCustomOverlay();
            this.replaceAppsMenuButton();
        });
    },

    openCustomHomeMenu() {
        this.state.isCustomHomeMenuOpen = true;
        document.body.style.overflow = 'hidden';
        this.renderCustomOverlay();
    },

    closeCustomHomeMenu() {
        this.state.isCustomHomeMenuOpen = false;
        document.body.style.overflow = '';
        this.renderCustomOverlay();
    },

    onAppClick(ev, app) {
        this.closeCustomHomeMenu();
        this.onNavBarDropdownItemSelection(app);
    },

    replaceAppsMenuButton() {
        // Find the default apps menu
        const appsMenuContainer = document.querySelector('.o_navbar_apps_menu');
        console.log("Apps menu container found:", appsMenuContainer);

        if (appsMenuContainer && !appsMenuContainer.classList.contains('custom-replaced')) {
            // Mark as replaced to avoid re-processing
            appsMenuContainer.classList.add('custom-replaced');

            // Use the standard 3x3 grid icon
            appsMenuContainer.innerHTML = `
                <button class="custom_home_menu_button border-0 bg-transparent" 
                        data-hotkey="h" 
                        title="Home Menu">
                    <i class="oi oi-apps"></i>
                </button>
            `;

            // Attach click handler
            const customButton = appsMenuContainer.querySelector('.custom_home_menu_button');
            if (customButton) {
                customButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.openCustomHomeMenu();
                });
            }
        }
    },

    renderCustomOverlay() {
        // Find or create overlay container
        let overlayContainer = document.getElementById('custom_home_menu_overlay_container');
        if (!overlayContainer) {
            overlayContainer = document.createElement('div');
            overlayContainer.id = 'custom_home_menu_overlay_container';
            document.body.appendChild(overlayContainer);
        }

        // Clear and render overlay if open
        overlayContainer.innerHTML = '';
        if (this.state.isCustomHomeMenuOpen) {
            const overlayHtml = this.renderOverlayHTML();
            overlayContainer.innerHTML = overlayHtml;
            this.attachOverlayEventListeners(overlayContainer);
        }
    },

    renderOverlayHTML() {
        const apps = this.menuService.getApps();
        const appCards = apps.map(app => {
            const iconHtml = app.webIconData
                ? `<img src="${app.webIconData}" alt=""/>`
                : `<i class="oi oi-apps"></i>`;

            return `
                <a href="${this.getMenuItemHref(app)}" 
                   class="custom_home_menu_app_card"
                   data-menu-xmlid="${app.xmlid}"
                   data-section="${app.id}"
                   data-app-id="${app.id}">
                  <div class="custom_home_menu_app_icon">
                    ${iconHtml}
                  </div>
                  <div class="custom_home_menu_app_name">${app.name}</div>
                </a>
            `;
        }).join('');

        return `
            <div class="custom_home_menu_overlay">
              <div class="custom_home_menu_container">
                <div class="custom_home_menu_grid">
                  ${appCards}
                </div>
              </div>
            </div>
        `;
    },

    attachOverlayEventListeners(container) {
        // Overlay background (click outside to close)
        const overlay = container.querySelector('.custom_home_menu_overlay');
        if (overlay) {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    this.closeCustomHomeMenu();
                }
            });
        }

        // App cards
        const appCards = container.querySelectorAll('.custom_home_menu_app_card');
        appCards.forEach(card => {
            card.addEventListener('click', (e) => {
                e.preventDefault();
                const appId = parseInt(card.dataset.appId);
                const app = this.menuService.getApps().find(a => a.id === appId);
                if (app) {
                    this.onAppClick(e, app);
                }
            });
        });
    },
});
