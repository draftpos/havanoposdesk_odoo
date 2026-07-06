/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { ListController } from "@web/views/list/list_controller";
import { onMounted, onPatched, onWillUnmount, useRef } from "@odoo/owl";
import { useBus } from "@web/core/utils/hooks";
import { NavBar } from "@web/webclient/navbar/navbar";
const MOBILE_MODELS = [
    'havanoposdesk.sale',
    'havanoposdesk.purchase',
    'havanoposdesk.customer',
    'havanoposdesk.customer.group',
    'havanoposdesk.cashier.sales.report',
    'havanoposdesk.category.sales.report',
    'havanoposdesk.daily.sales.report',
    'havanoposdesk.item.profitability.report',
    'havanoposdesk.terminal.sales.report',
    'havanoposdesk.product',
    'havanoposdesk.pricelist',
    'havanoposdesk.category',
    'havanoposdesk.uom',
    'havanoposdesk.stock.adjustment',
    'havanoposdesk.stock.valuation',
    'havanoposdesk.stock.ledger',
    'havanoposdesk.supplier'
];

// Patch KanbanController (Mobile -> Desktop switch & Header)
patch(KanbanController.prototype, {
    setup() {
        super.setup(...arguments);
        this.rootRef = useRef("root");
        
        this._handleKanbanResize = () => {
            if (!this.rootRef || !this.rootRef.el) return;
            
            // Check if this kanban view has our custom class
            const rendererEl = this.rootRef.el.querySelector('.havano_mobile_kanban');
            if (!rendererEl) return;
            
            if (window.innerWidth > 768) {
                // Remove header if it was added previously
                const existingHeader = this.rootRef.el.querySelector('.havano-mobile-header');
                if (existingHeader) existingHeader.remove();
                
                // Remove button styling
                const actionManager = this.rootRef.el.closest('.o_action_manager');
                if (actionManager) {
                    const createBtn = actionManager.querySelector('.o_control_panel .o_cp_bottom_right .o_cp_primary .btn-primary');
                    if (createBtn && createBtn.classList.contains('havano-button-styled')) {
                        createBtn.innerHTML = 'New';
                        createBtn.classList.remove('havano-button-styled');
                    }
                }

                // Auto-switch back to the normal list view on big screens
                if (this.env && this.env.services && this.env.services.action) {
                    setTimeout(() => {
                        this.env.services.action.switchView('list');
                    }, 50);
                }
            } else {
                this._injectHavanoHeader(rendererEl);
            }
        };

        onMounted(() => {
            window.addEventListener('resize', this._handleKanbanResize);
            this._handleKanbanResize();
        });
        
        onPatched(() => {
            this._handleKanbanResize();
        });

        onWillUnmount(() => {
            window.removeEventListener('resize', this._handleKanbanResize);
        });
    },

    _injectHavanoHeader(rendererEl) {
        let headerEl = this.rootRef.el.querySelector('.havano-mobile-header');
        
        const records = this.props.list.records;
        let total = 0;
        let hasTotal = false;

        // Calculate the sum of amount_total or total_sales depending on the model
        records.forEach(rec => {
            if (rec.data.amount_total) {
                total += rec.data.amount_total;
                hasTotal = true;
            } else if (rec.data.total_sales) {
                total += rec.data.total_sales;
                hasTotal = true;
            }
        });
        
        const formattedTotal = total.toLocaleString('en-US', { style: 'currency', currency: 'USD' });

        if (hasTotal) {
            if (!headerEl) {
                headerEl = document.createElement('div');
                headerEl.className = 'havano-mobile-header';
                headerEl.innerHTML = `<span>Total</span><span class="total-amount">${formattedTotal}</span>`;
                rendererEl.parentNode.insertBefore(headerEl, rendererEl);
            } else {
                headerEl.querySelector('.total-amount').textContent = formattedTotal;
            }
        }

        // Style create button
        const actionManager = this.rootRef.el.closest('.o_action_manager');
        if (actionManager) {
            const createBtn = actionManager.querySelector('.o_control_panel .o_cp_bottom_right .o_cp_primary .btn-primary');
            if (createBtn && !createBtn.classList.contains('havano-button-styled')) {
                const modelName = this.props.list.resModel;
                let btnText = "Add";
                if (modelName === 'havanoposdesk.sale') btnText = "Add Sale";
                else if (modelName === 'havanoposdesk.purchase') btnText = "Add Purchase";
                else if (modelName === 'havanoposdesk.customer') btnText = "Add Customer";
                else if (modelName === 'havanoposdesk.customer.group') btnText = "Add Group";
                else if (modelName === 'havanoposdesk.product') btnText = "Add Product";
                else if (modelName === 'havanoposdesk.pricelist') btnText = "Add Pricelist";
                else if (modelName === 'havanoposdesk.category') btnText = "Add Category";
                else if (modelName === 'havanoposdesk.uom') btnText = "Add UOM";
                else if (modelName === 'havanoposdesk.stock.adjustment') btnText = "Add Adjustment";
                else if (modelName === 'havanoposdesk.supplier') btnText = "Add Supplier";
                
                createBtn.innerHTML = `&nbsp; ${btnText}`;
                createBtn.classList.add('havano-button-styled');
            }
        }
    }
});

// Patch ListController (Desktop -> Mobile switch)
patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        
        this._handleListResize = () => {
            const modelName = this.props.resModel;
            // Apply auto-switch for targeted models
            if (!MOBILE_MODELS.includes(modelName)) return;

            if (window.innerWidth <= 768) {
                // Auto-switch to kanban view on small screens using action service
                if (this.env && this.env.services && this.env.services.action) {
                    setTimeout(() => {
                        this.env.services.action.switchView('kanban');
                    }, 50);
                }
            }
        };

        onMounted(() => {
            window.addEventListener('resize', this._handleListResize);
            // Slight delay on initial mount to ensure control panel buttons are rendered
            setTimeout(() => this._handleListResize(), 50);
        });
        
        onWillUnmount(() => {
            window.removeEventListener('resize', this._handleListResize);
        });
    }
});

// Patch NavBar to automatically open the AppMenuSidebar on mobile when switching apps
patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        
        let appJustChanged = false;

        // Listen for when an app is selected from the home menu
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => {
            appJustChanged = true;
            // Clear the flag after a short delay
            setTimeout(() => { appJustChanged = false; }, 800);
        });

        // Intercept the default action load and open the App Menu Sidebar
        useBus(this.env.bus, "ACTION_MANAGER:UPDATE", () => {
            if (appJustChanged && window.innerWidth <= 768) {
                const currentApp = this.env.services.menu && this.env.services.menu.getCurrentApp();
                // Do not auto-open sidebar if it's the Dashboard
                if (!currentApp || currentApp.xmlid !== "Havanoposdesk_odoo.menu_dashboard_main") {
                    // Force open the App Menu Sidebar (which contains the app's modules/dropdown)
                    setTimeout(() => {
                        this.state.isAppMenuSidebarOpened = true;
                    }, 50);
                }
                appJustChanged = false;
            }
        });
    }
});

// Capture PWA install prompt globally so components can use it later
window.deferredPwaPrompt = null;
window.addEventListener('beforeinstallprompt', (e) => {
    // Prevent the mini-infobar from appearing on mobile
    e.preventDefault();
    // Stash the event so it can be triggered later.
    window.deferredPwaPrompt = e;
});
