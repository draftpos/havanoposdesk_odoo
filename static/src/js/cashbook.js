/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

export class CashbookReport extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        
        this.state = useState({
            data: {
                currency_symbol: '$',
                opening_balance: 0.0,
                total_inflows: 0.0,
                total_outflows: 0.0,
                closing_balance: 0.0,
                net_movement: 0.0,
                breakdown: {
                    sales: 0.0,
                    customer_receipts: 0.0,
                    transfers_in: 0.0,
                    expenses: 0.0,
                    supplier_payments: 0.0,
                    transfers_out: 0.0
                },
                accounts: [],
                movements: [],
                total_transactions: 0
            },
            isLoading: true,
            dateFrom: "",
            dateTo: "",
            datePreset: "this_year",
            availableStores: [],
            selectedStoreId: "all",
            availableAccounts: [],
            selectedAccountId: "all",
            searchQuery: "",
            typeFilter: "all",
            months: [
                { id: 'month_0', name: 'January' }, { id: 'month_1', name: 'February' },
                { id: 'month_2', name: 'March' }, { id: 'month_3', name: 'April' },
                { id: 'month_4', name: 'May' }, { id: 'month_5', name: 'June' },
                { id: 'month_6', name: 'July' }, { id: 'month_7', name: 'August' },
                { id: 'month_8', name: 'September' }, { id: 'month_9', name: 'October' },
                { id: 'month_10', name: 'November' }, { id: 'month_11', name: 'December' }
            ],
            quarters: [
                { id: 'quarter_0', name: 'Q1' }, { id: 'quarter_1', name: 'Q2' },
                { id: 'quarter_2', name: 'Q3' }, { id: 'quarter_3', name: 'Q4' }
            ]
        });

        onWillStart(() => {
            this.loadInitialFilters().then(() => {
                this.setPresetDates('this_year');
                this.loadData();
            }).catch((err) => {
                console.error("Failed to initialize cashbook:", err);
                this.state.isLoading = false;
            });
        });
    }

    async loadInitialFilters() {
        try {
            const stores = await this.orm.call("havanoposdesk.cashbook", "get_available_stores", []);
            this.state.availableStores = Array.isArray(stores) ? stores : [];
        } catch (e) {
            console.error("Failed to load stores:", e);
            this.state.availableStores = [];
        }

        try {
            const accounts = await this.orm.call("havanoposdesk.cashbook", "get_available_accounts", []);
            this.state.availableAccounts = Array.isArray(accounts) ? accounts : [];
        } catch (e) {
            console.error("Failed to load accounts:", e);
            this.state.availableAccounts = [];
        }
    }

    setPresetDates(preset) {
        this.state.datePreset = preset;
        const now = new Date();
        const currentYear = now.getFullYear();
        const pad = (n) => String(n).padStart(2, '0');

        if (preset === 'this_year') {
            this.state.dateFrom = `${currentYear}-01-01`;
            this.state.dateTo = `${currentYear}-12-31`;
        } else if (preset === 'this_month') {
            const firstDay = new Date(currentYear, now.getMonth(), 1);
            const lastDay = new Date(currentYear, now.getMonth() + 1, 0);
            this.state.dateFrom = `${firstDay.getFullYear()}-${pad(firstDay.getMonth() + 1)}-${pad(firstDay.getDate())}`;
            this.state.dateTo = `${lastDay.getFullYear()}-${pad(lastDay.getMonth() + 1)}-${pad(lastDay.getDate())}`;
        } else if (preset === 'last_month') {
            const firstDay = new Date(currentYear, now.getMonth() - 1, 1);
            const lastDay = new Date(currentYear, now.getMonth(), 0);
            this.state.dateFrom = `${firstDay.getFullYear()}-${pad(firstDay.getMonth() + 1)}-${pad(firstDay.getDate())}`;
            this.state.dateTo = `${lastDay.getFullYear()}-${pad(lastDay.getMonth() + 1)}-${pad(lastDay.getDate())}`;
        } else if (preset === 'this_quarter') {
            const quarter = Math.floor(now.getMonth() / 3);
            const firstDay = new Date(currentYear, quarter * 3, 1);
            const lastDay = new Date(currentYear, quarter * 3 + 3, 0);
            this.state.dateFrom = `${firstDay.getFullYear()}-${pad(firstDay.getMonth() + 1)}-${pad(firstDay.getDate())}`;
            this.state.dateTo = `${lastDay.getFullYear()}-${pad(lastDay.getMonth() + 1)}-${pad(lastDay.getDate())}`;
        } else if (preset === 'last_year') {
            this.state.dateFrom = `${currentYear - 1}-01-01`;
            this.state.dateTo = `${currentYear - 1}-12-31`;
        } else if (preset === 'today') {
            const todayStr = `${currentYear}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
            this.state.dateFrom = todayStr;
            this.state.dateTo = todayStr;
        } else if (preset === 'yesterday') {
            const yest = new Date(now);
            yest.setDate(now.getDate() - 1);
            const yestStr = `${yest.getFullYear()}-${pad(yest.getMonth() + 1)}-${pad(yest.getDate())}`;
            this.state.dateFrom = yestStr;
            this.state.dateTo = yestStr;
        } else if (preset.startsWith('month_')) {
            const m = parseInt(preset.split('_')[1]);
            const firstDay = new Date(currentYear, m, 1);
            const lastDay = new Date(currentYear, m + 1, 0);
            this.state.dateFrom = `${firstDay.getFullYear()}-${pad(firstDay.getMonth() + 1)}-${pad(firstDay.getDate())}`;
            this.state.dateTo = `${lastDay.getFullYear()}-${pad(lastDay.getMonth() + 1)}-${pad(lastDay.getDate())}`;
        } else if (preset.startsWith('quarter_')) {
            const q = parseInt(preset.split('_')[1]);
            const firstDay = new Date(currentYear, q * 3, 1);
            const lastDay = new Date(currentYear, q * 3 + 3, 0);
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

    async onFilterChange() {
        this.state.datePreset = 'custom';
        await this.loadData();
    }

    async selectStore(storeId) {
        this.state.selectedStoreId = String(storeId);
        await this.loadData();
    }

    async selectAccount(accountId) {
        this.state.selectedAccountId = String(accountId);
        await this.loadData();
    }

    isStoreSelected(storeId) {
        return String(this.state.selectedStoreId) === String(storeId);
    }

    isAccountSelected(accountId) {
        return String(this.state.selectedAccountId) === String(accountId);
    }

    get selectedStoreLabel() {
        if (!this.state.selectedStoreId || this.state.selectedStoreId === 'all') return 'All Stores';
        const st = this.state.availableStores.find(s => String(s.id) === String(this.state.selectedStoreId));
        return st ? st.name : 'All Stores';
    }

    get selectedAccountLabel() {
        if (!this.state.selectedAccountId || this.state.selectedAccountId === 'all') return 'All Accounts';
        const acc = this.state.availableAccounts.find(a => String(a.id) === String(this.state.selectedAccountId));
        return acc ? acc.name : 'All Accounts';
    }

    get datePresetLabel() {
        const p = this.state.datePreset;
        if (p === 'this_month') return 'This Month';
        if (p === 'this_quarter') return 'This Quarter';
        if (p === 'this_year') return 'This Year';
        if (p === 'last_month') return 'Last Month';
        if (p === 'last_year') return 'Last Year';
        if (p === 'today') return 'Today';
        if (p === 'yesterday') return 'Yesterday';
        if (p === 'all') return 'All Time';
        if (p && p.startsWith('month_')) {
            const m = this.state.months.find(item => item.id === p);
            return m ? m.name : p;
        }
        if (p && p.startsWith('quarter_')) {
            const q = this.state.quarters.find(item => item.id === p);
            return q ? q.name : p;
        }
        if (this.state.dateFrom && this.state.dateTo) {
            return `${this.state.dateFrom} to ${this.state.dateTo}`;
        }
        if (this.state.dateFrom) return `From ${this.state.dateFrom}`;
        if (this.state.dateTo) return `To ${this.state.dateTo}`;
        return 'All Time';
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
            if (res) {
                this.state.data = res;
            }
        } catch (err) {
            console.error("Error loading cashbook data:", err);
        } finally {
            this.state.isLoading = false;
        }
    }

    getBreakdown(key) {
        if (this.state.data && this.state.data.breakdown && this.state.data.breakdown[key] !== undefined) {
            return this.state.data.breakdown[key];
        }
        return 0.0;
    }

    get filteredMovements() {
        if (!this.state.data || !this.state.data.movements) return [];
        let items = this.state.data.movements;
        if (this.state.typeFilter !== 'all') {
            items = items.filter(m => m.type === this.state.typeFilter);
        }
        if (this.state.searchQuery && this.state.searchQuery.trim()) {
            const q = this.state.searchQuery.toLowerCase().trim();
            items = items.filter(m => 
                (m.reference && m.reference.toLowerCase().includes(q)) ||
                (m.party && m.party.toLowerCase().includes(q)) ||
                (m.account_name && m.account_name.toLowerCase().includes(q)) ||
                (m.store_name && m.store_name.toLowerCase().includes(q)) ||
                (m.note && m.note.toLowerCase().includes(q)) ||
                (m.type_label && m.type_label.toLowerCase().includes(q))
            );
        }
        return items;
    }

    formatCurrency(amount) {
        const sym = (this.state.data && this.state.data.currency_symbol) ? this.state.data.currency_symbol : '$';
        const val = parseFloat(amount || 0).toFixed(2);
        return `${sym}${Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }

    printReport() {
        window.print();
    }
}

CashbookReport.template = "havanoposdesk.CashbookReport";
registry.category("actions").add("havanoposdesk_cashbook", CashbookReport);
