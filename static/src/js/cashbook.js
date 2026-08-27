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
            dateFrom: "",
            dateTo: "",
            datePreset: "this_year",
            comparison: "none",
            inflowsExpanded: false,
            outflowsExpanded: false,
            accountsExpanded: true,
            availableStores: [],
            selectedStores: [],
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
            this.loadStores().then(() => {
                this.setPresetDates('this_year');
                this.loadData();
            });
        });
    }

    async loadStores() {
        try {
            const stores = await this.orm.call(
                "havanoposdesk.cashbook",
                "get_available_stores",
                []
            );
            this.state.availableStores = Array.isArray(stores) ? stores : [];
            this.state.selectedStores = this.state.availableStores.map(s => s.id);
        } catch (e) {
            console.error("Failed to load stores:", e);
            this.state.availableStores = [];
            this.state.selectedStores = [];
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
        } else if (preset === 'last_year') {
            this.state.dateFrom = `${currentYear - 1}-01-01`;
            this.state.dateTo = `${currentYear - 1}-12-31`;
        } else if (preset === 'this_quarter') {
            const quarter = Math.floor(now.getMonth() / 3);
            const firstDay = new Date(currentYear, quarter * 3, 1);
            const lastDay = new Date(currentYear, quarter * 3 + 3, 0);
            this.state.dateFrom = `${firstDay.getFullYear()}-${pad(firstDay.getMonth() + 1)}-${pad(firstDay.getDate())}`;
            this.state.dateTo = `${lastDay.getFullYear()}-${pad(lastDay.getMonth() + 1)}-${pad(lastDay.getDate())}`;
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
        } else if (preset === 'custom') {
            // Keep current dates
        }
    }

    async applyPreset(preset) {
        this.setPresetDates(preset);
        await this.loadData();
    }

    async setComparison(comp) {
        this.state.comparison = comp;
        await this.loadData();
    }

    toggleStore(storeId) {
        const index = this.state.selectedStores.indexOf(storeId);
        if (index > -1) {
            this.state.selectedStores.splice(index, 1);
        } else {
            this.state.selectedStores.push(storeId);
        }
        this.loadData();
    }

    get selectedStoreNames() {
        return this.state.availableStores
            .filter(s => this.state.selectedStores.includes(s.id))
            .map(s => s.name);
    }

    async loadData() {
        try {
            const result = await this.orm.call(
                "havanoposdesk.cashbook",
                "get_report_data",
                [],
                {
                    date_from: this.state.dateFrom || null,
                    date_to: this.state.dateTo || null,
                    store_ids: this.state.selectedStores.length > 0 ? this.state.selectedStores : null,
                    comparison: this.state.comparison
                }
            );
            this.state.data = result;
        } catch (e) {
            console.error("Error loading cashbook data:", e);
        }
    }

    async onFilterChange() {
        this.state.datePreset = 'custom';
        await this.loadData();
    }

    formatCurrency(amount) {
        if (amount === undefined || amount === null) return "$0.00";
        const sym = (this.state.data && this.state.data.currency_symbol) ? this.state.data.currency_symbol : "$";
        const val = parseFloat(amount || 0).toFixed(2);
        return `${sym}${Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }

    toggleInflows() {
        this.state.inflowsExpanded = !this.state.inflowsExpanded;
    }

    toggleOutflows() {
        this.state.outflowsExpanded = !this.state.outflowsExpanded;
    }

    toggleAccounts() {
        this.state.accountsExpanded = !this.state.accountsExpanded;
    }

    printReport() {
        window.print();
    }
}

CashbookReport.template = "havanoposdesk.CashbookReport";
registry.category("actions").add("havanoposdesk_cashbook", CashbookReport);
