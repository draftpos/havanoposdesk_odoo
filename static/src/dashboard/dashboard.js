/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, useState, useRef, onWillUnmount } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";

export class HavanoDashboard extends Component {
    static template = "havanoposdesk_odoo.Dashboard";
    static components = { Dropdown, DropdownItem };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        
        this.state = useState({
            kpis: {
                gross_sales: 0,
                net_sales: 0,
                cost_of_sales: 0,
                gross_profit: 0
            },
            stock_stats: {
                total_valuation: 0,
                total_items: 0
            },
            period: 'today',
            periodLabel: 'Today'
        });

        this.salesChartRef = useRef("salesChart");
        this.stockChartRef = useRef("stockChart");
        this.salesChartInstance = null;
        this.stockChartInstance = null;

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.fetchData();
        });

        onMounted(() => {
            this.renderCharts();
            window.addEventListener('resize', this.onResize);
        });
        
        onWillUnmount(() => {
            window.removeEventListener('resize', this.onResize);
            if (this.salesChartInstance) this.salesChartInstance.destroy();
            if (this.stockChartInstance) this.stockChartInstance.destroy();
        });
    }
    
    onResize = () => {
        if (this.salesChartInstance) this.salesChartInstance.resize();
        if (this.stockChartInstance) this.stockChartInstance.resize();
    }

    async fetchData() {
        // Calculate date range based on period
        let date_from = null;
        let date_to = null;
        const now = new Date();
        
        const formatDate = (date) => {
            const d = new Date(date);
            let month = '' + (d.getMonth() + 1);
            let day = '' + d.getDate();
            const year = d.getFullYear();

            if (month.length < 2) month = '0' + month;
            if (day.length < 2) day = '0' + day;

            return [year, month, day].join('-');
        }

        date_to = formatDate(now);
        
        if (this.state.period === 'today') {
            date_from = formatDate(now);
        } else if (this.state.period === 'yesterday') {
            const y = new Date(now);
            y.setDate(now.getDate() - 1);
            date_from = formatDate(y);
            date_to = formatDate(y);
        } else if (this.state.period === 'this_week') {
            const w = new Date(now);
            const diff = now.getDate() - now.getDay() + (now.getDay() === 0 ? -6 : 1);
            w.setDate(diff);
            date_from = formatDate(w);
        } else if (this.state.period === 'last_week') {
            const w = new Date(now);
            const diff = now.getDate() - now.getDay() - 6;
            w.setDate(diff);
            date_from = formatDate(w);
            const end_w = new Date(w);
            end_w.setDate(w.getDate() + 6);
            date_to = formatDate(end_w);
        } else if (this.state.period === 'this_month') {
            const m = new Date(now.getFullYear(), now.getMonth(), 1);
            date_from = formatDate(m);
        } else if (this.state.period === 'last_month') {
            const m = new Date(now.getFullYear(), now.getMonth() - 1, 1);
            date_from = formatDate(m);
            const end_m = new Date(now.getFullYear(), now.getMonth(), 0);
            date_to = formatDate(end_m);
        }

        const data = await this.orm.call(
            "havanoposdesk.dashboard",
            "get_dashboard_data",
            [date_from, date_to]
        );

        if (data && data.kpis) {
            Object.assign(this.state.kpis, data.kpis);
            Object.assign(this.state.stock_stats, data.stock_stats);
            this.salesChartData = data.sales_chart;
            this.stockChartData = data.stock_chart;
        } else {
            // Default to empty state if no tenant_id or no data returned
            Object.assign(this.state.kpis, { gross_sales: 0, net_sales: 0, cost_of_sales: 0, gross_profit: 0 });
            Object.assign(this.state.stock_stats, { total_valuation: 0, total_items: 0 });
            this.salesChartData = { labels: [], datasets: [] };
            this.stockChartData = { labels: [], valuation: [] };
        }
    }

    async setPeriod(period, label) {
        this.state.period = period;
        this.state.periodLabel = label;
        await this.fetchData();
        this.renderCharts();
    }

    formatCurrency(value) {
        return Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    renderCharts() {
        // Sales Summary Chart
        if (this.salesChartInstance) {
            this.salesChartInstance.destroy();
        }
        if (this.salesChartRef.el && this.salesChartData) {
            const ctx = this.salesChartRef.el.getContext('2d');
            this.salesChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: this.salesChartData.labels,
                    datasets: [
                        {
                            label: 'Gross profit',
                            data: this.salesChartData.gross_profit,
                            borderColor: '#f39c12',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            tension: 0.1
                        },
                        {
                            label: 'Net sales',
                            data: this.salesChartData.net_sales,
                            borderColor: '#2ecc71',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            tension: 0.1
                        },
                        {
                            label: 'Cost of sales',
                            data: this.salesChartData.cost_of_sales,
                            borderColor: '#9b59b6',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            tension: 0.1
                        },
                        {
                            label: 'Gross sales',
                            data: this.salesChartData.gross_sales,
                            borderColor: '#3498db',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            tension: 0.1
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'top',
                            align: 'end',
                            labels: { boxWidth: 8, usePointStyle: true, pointStyle: 'circle' }
                        }
                    },
                    scales: {
                        y: { beginAtZero: true, grid: { borderDash: [2, 4] } },
                        x: { grid: { display: false } }
                    }
                }
            });
        }

        // Stock Valuation Chart
        if (this.stockChartInstance) {
            this.stockChartInstance.destroy();
        }
        if (this.stockChartRef.el && this.stockChartData) {
            const ctx = this.stockChartRef.el.getContext('2d');
            this.stockChartInstance = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: this.stockChartData.labels,
                    datasets: [
                        {
                            label: 'Valuation',
                            data: this.stockChartData.valuation,
                            backgroundColor: '#3498db',
                            borderRadius: 4
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'top',
                            align: 'end',
                            labels: { boxWidth: 8, usePointStyle: true, pointStyle: 'circle' }
                        }
                    },
                    scales: {
                        y: { beginAtZero: true, grid: { borderDash: [2, 4] } },
                        x: { grid: { display: false } }
                    }
                }
            });
        }
    }
}

registry.category("actions").add("havano_dashboard_tag", HavanoDashboard);
