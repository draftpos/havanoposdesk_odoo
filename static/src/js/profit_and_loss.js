/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

export class ProfitAndLossReport extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        
        this.state = useState({
            data: null,
            dateFrom: "",
            dateTo: "",
            datePreset: "this_year",
            comparison: "none",
            expensesExpanded: false,
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

        onWillStart(async () => {
            await this.loadStores();
            this.setPresetDates('this_year');
            await this.loadData();
        });
    }

    async loadStores() {
        const stores = await this.orm.call(
            "havanoposdesk.profit.and.loss",
            "get_available_stores",
            []
        );
        this.state.availableStores = stores;
    }

    setPresetDates(preset) {
        this.state.datePreset = preset;
        const now = new Date();
        const currentYear = now.getFullYear();
        if (preset === 'this_year') {
            this.state.dateFrom = `${currentYear}-01-01`;
            this.state.dateTo = `${currentYear}-12-31`;
        } else if (preset === 'this_month') {
            const firstDay = new Date(currentYear, now.getMonth(), 1);
            const lastDay = new Date(currentYear, now.getMonth() + 1, 0);
            this.state.dateFrom = firstDay.toISOString().split('T')[0];
            this.state.dateTo = lastDay.toISOString().split('T')[0];
        } else if (preset === 'last_month') {
            const firstDay = new Date(currentYear, now.getMonth() - 1, 1);
            const lastDay = new Date(currentYear, now.getMonth(), 0);
            this.state.dateFrom = firstDay.toISOString().split('T')[0];
            this.state.dateTo = lastDay.toISOString().split('T')[0];
        } else if (preset === 'last_year') {
            this.state.dateFrom = `${currentYear - 1}-01-01`;
            this.state.dateTo = `${currentYear - 1}-12-31`;
        } else if (preset === 'this_quarter') {
            const quarter = Math.floor(now.getMonth() / 3);
            const firstDay = new Date(currentYear, quarter * 3, 1);
            const lastDay = new Date(currentYear, quarter * 3 + 3, 0);
            this.state.dateFrom = firstDay.toISOString().split('T')[0];
            this.state.dateTo = lastDay.toISOString().split('T')[0];
        } else if (preset.startsWith('month_')) {
            const m = parseInt(preset.split('_')[1]);
            const firstDay = new Date(currentYear, m, 1);
            const lastDay = new Date(currentYear, m + 1, 0);
            this.state.dateFrom = firstDay.toISOString().split('T')[0];
            this.state.dateTo = lastDay.toISOString().split('T')[0];
        } else if (preset.startsWith('quarter_')) {
            const q = parseInt(preset.split('_')[1]);
            const firstDay = new Date(currentYear, q * 3, 1);
            const lastDay = new Date(currentYear, q * 3 + 3, 0);
            this.state.dateFrom = firstDay.toISOString().split('T')[0];
            this.state.dateTo = lastDay.toISOString().split('T')[0];
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
        // Fetch data from the python model
        const result = await this.orm.call(
            "havanoposdesk.profit.and.loss",
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
    }

    async onFilterChange() {
        this.state.datePreset = 'custom';
        await this.loadData();
    }

    async downloadPDF() {
        // Download PDF action
        this.action.doAction({
            type: 'ir.actions.report',
            report_type: 'qweb-pdf',
            report_name: 'havanoposdesk.report_profit_and_loss',
            report_file: 'havanoposdesk.report_profit_and_loss',
            data: {
                date_from: this.state.dateFrom || null,
                date_to: this.state.dateTo || null,
                store_ids: this.state.selectedStores.length > 0 ? this.state.selectedStores : null,
                comparison: this.state.comparison
            }
        });
    }

    toggleExpenses() {
        this.state.expensesExpanded = !this.state.expensesExpanded;
    }
    
    formatCurrency(amount) {
        // Simple currency formatter
        if (amount === null || amount === undefined) return "0.00";
        return amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
}

ProfitAndLossReport.template = "havanoposdesk.ProfitAndLossReport";

registry.category("actions").add("havanoposdesk_profit_and_loss", ProfitAndLossReport);
