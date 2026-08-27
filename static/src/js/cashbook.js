/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

export class CashbookReport extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        
        this.state = useState({
            data: null,
            isLoading: true,
            dateFrom: "",
            dateTo: "",
            datePreset: "today",
            availableStores: [],
            selectedStoreId: "all",
            availableAccounts: [],
            selectedAccountId: "all",
            searchQuery: "",
            typeFilter: "all"
        });

        onWillStart(async () => {
            await this.loadInitialFilters();
            this.setPresetDates('today');
            await this.loadData();
        });
    }

    async loadInitialFilters() {
        try {
            const stores = await this.orm.call("havanoposdesk.cashbook", "get_available_stores", []);
            this.state.availableStores = stores || [];
            
            const accounts = await this.orm.call("havanoposdesk.cashbook", "get_available_accounts", []);
            this.state.availableAccounts = accounts || [];
        } catch (e) {
            console.error("Failed to load initial filters:", e);
        }
    }

    setPresetDates(preset) {
        this.state.datePreset = preset;
        const now = new Date();
        const year = now.getFullYear();
        const pad = (n) => String(n).padStart(2, '0');
        const todayStr = `${year}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;

        if (preset === 'today') {
            this.state.dateFrom = todayStr;
            this.state.dateTo = todayStr;
        } else if (preset === 'yesterday') {
            const yest = new Date(now);
            yest.setDate(now.getDate() - 1);
            const yestStr = `${yest.getFullYear()}-${pad(yest.getMonth() + 1)}-${pad(yest.getDate())}`;
            this.state.dateFrom = yestStr;
            this.state.dateTo = yestStr;
        } else if (preset === 'this_week') {
            const first = now.getDate() - now.getDay();
            const firstDay = new Date(now.setDate(first));
            const lastDay = new Date(now.setDate(first + 6));
            this.state.dateFrom = `${firstDay.getFullYear()}-${pad(firstDay.getMonth() + 1)}-${pad(firstDay.getDate())}`;
            this.state.dateTo = `${lastDay.getFullYear()}-${pad(lastDay.getMonth() + 1)}-${pad(lastDay.getDate())}`;
        } else if (preset === 'this_month') {
            const firstDay = new Date(year, now.getMonth(), 1);
            const lastDay = new Date(year, now.getMonth() + 1, 0);
            this.state.dateFrom = `${year}-${pad(firstDay.getMonth() + 1)}-${pad(firstDay.getDate())}`;
            this.state.dateTo = `${year}-${pad(lastDay.getMonth() + 1)}-${pad(lastDay.getDate())}`;
        } else if (preset === 'last_month') {
            const firstDay = new Date(year, now.getMonth() - 1, 1);
            const lastDay = new Date(year, now.getMonth(), 0);
            this.state.dateFrom = `${firstDay.getFullYear()}-${pad(firstDay.getMonth() + 1)}-${pad(firstDay.getDate())}`;
            this.state.dateTo = `${lastDay.getFullYear()}-${pad(lastDay.getMonth() + 1)}-${pad(lastDay.getDate())}`;
        } else if (preset === 'all') {
            this.state.dateFrom = "";
            this.state.dateTo = "";
        }
    }

    async applyPreset(preset) {
        this.setPresetDates(preset);
        await this.loadData();
    }

    async onStoreChange(ev) {
        this.state.selectedStoreId = ev.target.value;
        await this.loadData();
    }

    async onAccountChange(ev) {
        this.state.selectedAccountId = ev.target.value;
        await this.loadData();
    }

    async onCustomDateChange() {
        this.state.datePreset = 'custom';
        await this.loadData();
    }

    async loadData() {
        this.state.isLoading = true;
        try {
            const storeIds = (this.state.selectedStoreId && this.state.selectedStoreId !== 'all') ? [parseInt(this.state.selectedStoreId)] : null;
            const accountIds = (this.state.selectedAccountId && this.state.selectedAccountId !== 'all') ? [parseInt(this.state.selectedAccountId)] : null;

            const res = await this.orm.call(
                "havanoposdesk.cashbook",
                "get_report_data",
                [],
                {
                    store_ids: storeIds,
                    account_ids: accountIds,
                    date_from: this.state.dateFrom || null,
                    date_to: this.state.dateTo || null,
                }
            );
            this.state.data = res;
        } catch (err) {
            console.error("Error loading cashbook data:", err);
        } finally {
            this.state.isLoading = false;
        }
    }

    get filteredMovements() {
        if (!this.state.data || !this.state.data.movements) return [];
        let items = this.state.data.movements;
        if (this.state.typeFilter !== 'all') {
            items = items.filter(m => m.type === this.state.typeFilter);
        }
        if (this.state.searchQuery.trim()) {
            const q = this.state.searchQuery.toLowerCase().trim();
            items = items.filter(m => 
                (m.reference && m.reference.toLowerCase().includes(q)) ||
                (m.party && m.party.toLowerCase().includes(q)) ||
                (m.account_name && m.account_name.toLowerCase().includes(q)) ||
                (m.store_name && m.store_name.toLowerCase().includes(q)) ||
                (m.note && m.note.toLowerCase().includes(q))
            );
        }
        return items;
    }

    formatCurrency(amount) {
        const sym = this.state.data ? this.state.data.currency_symbol : '$';
        const val = parseFloat(amount || 0).toFixed(2);
        return `${sym}${Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }

    printReport() {
        window.print();
    }
}

CashbookReport.template = "havanoposdesk.CashbookReport";
registry.category("actions").add("havanoposdesk_cashbook", CashbookReport);
