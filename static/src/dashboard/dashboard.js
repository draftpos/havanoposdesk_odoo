/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, useState, useRef, onWillUnmount } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { PwaPrompt } from "./pwa_prompt";

export class HavanoDashboard extends Component {
    static template = "havanoposdesk_odoo.Dashboard";
    static components = { Dropdown, DropdownItem, PwaPrompt };

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
            periodLabel: 'Today',
            customDateFrom: '',
            customDateTo: ''
        });

        this.salesChartRef = useRef("salesChart");
        this.stockChartRef = useRef("stockChart");
        this.sparklineGrossRef = useRef("sparklineGross");
        this.sparklineNetRef = useRef("sparklineNet");
        this.sparklineCostRef = useRef("sparklineCost");
        this.sparklineProfitRef = useRef("sparklineProfit");

        this.salesChartInstance = null;
        this.stockChartInstance = null;
        this.sparklineGrossInstance = null;
        this.sparklineNetInstance = null;
        this.sparklineCostInstance = null;
        this.sparklineProfitInstance = null;

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
            if (this.sparklineGrossInstance) this.sparklineGrossInstance.destroy();
            if (this.sparklineNetInstance) this.sparklineNetInstance.destroy();
            if (this.sparklineCostInstance) this.sparklineCostInstance.destroy();
            if (this.sparklineProfitInstance) this.sparklineProfitInstance.destroy();
        });
    }
    
    onResize = () => {
        if (this.salesChartInstance) this.salesChartInstance.resize();
        if (this.stockChartInstance) this.stockChartInstance.resize();
        if (this.sparklineGrossInstance) this.sparklineGrossInstance.resize();
        if (this.sparklineNetInstance) this.sparklineNetInstance.resize();
        if (this.sparklineCostInstance) this.sparklineCostInstance.resize();
        if (this.sparklineProfitInstance) this.sparklineProfitInstance.resize();
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
        } else if (this.state.period === 'custom') {
            date_from = this.state.customDateFrom;
            date_to = this.state.customDateTo;
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
            this.sparklineData = data.sparkline_data;
        } else {
            // Default to empty state if no tenant_id or no data returned
            Object.assign(this.state.kpis, { gross_sales: 0, net_sales: 0, cost_of_sales: 0, gross_profit: 0 });
            Object.assign(this.state.stock_stats, { total_valuation: 0, total_items: 0 });
            this.salesChartData = { labels: [], datasets: [] };
            this.stockChartData = { labels: [], valuation: [] };
            this.sparklineData = { labels: [], gross_sales: [], net_sales: [], cost_of_sales: [], gross_profit: [] };
        }
    }

    async setPeriod(period, label) {
        this.state.period = period;
        this.state.periodLabel = label;
        if (period !== 'custom') {
            await this.fetchData();
            this.renderCharts();
        }
    }

    async applyCustomDate() {
        if (this.state.customDateFrom && this.state.customDateTo) {
            this.state.periodLabel = `${this.state.customDateFrom} to ${this.state.customDateTo}`;
            await this.fetchData();
            this.renderCharts();
        }
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
                type: 'bar',
                data: {
                    labels: this.salesChartData.labels,
                    datasets: [
                        {
                            label: 'Gross profit',
                            data: this.salesChartData.gross_profit,
                            backgroundColor: '#f39c12',
                            borderRadius: 4,
                            maxBarThickness: 50
                        },
                        {
                            label: 'Net sales',
                            data: this.salesChartData.net_sales,
                            backgroundColor: '#2ecc71',
                            borderRadius: 4,
                            maxBarThickness: 50
                        },
                        {
                            label: 'Cost of sales',
                            data: this.salesChartData.cost_of_sales,
                            backgroundColor: '#9b59b6',
                            borderRadius: 4,
                            maxBarThickness: 50
                        },
                        {
                            label: 'Gross sales',
                            data: this.salesChartData.gross_sales,
                            backgroundColor: '#3498db',
                            borderRadius: 4,
                            maxBarThickness: 50
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
                            borderRadius: 4,
                            maxBarThickness: 50
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

        // Helper to render sparklines
        const renderSparkline = (ref, instance, data, labels, color) => {
            if (instance) instance.destroy();
            if (ref.el && data) {
                const is_empty = data.length === 0;
                const chartData = is_empty ? [0, 0] : data;
                const chartLabels = is_empty ? ['', ''] : labels;
                const minVal = Math.min(...chartData);
                const maxVal = Math.max(...chartData);
                
                const ctx = ref.el.getContext('2d');
                return new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: chartLabels,
                        datasets: [{
                            data: chartData,
                            borderColor: color,
                            borderWidth: 1.5,
                            tension: 0.1,
                            fill: false,
                            pointRadius: 0,
                            pointHoverRadius: 0
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false }, tooltip: { enabled: false } },
                        scales: {
                            x: { 
                                display: true, 
                                grid: { display: true, drawBorder: false, color: '#e0e0e0', borderDash: [2, 2] },
                                ticks: { display: false }
                            },
                            y: { 
                                display: false, 
                                min: minVal === maxVal ? minVal - 1 : minVal * 0.9, 
                                max: minVal === maxVal ? maxVal + 1 : maxVal * 1.1 
                            }
                        },
                        layout: { padding: 0 }
                    }
                });
            }
            return null;
        };

        if (this.sparklineData) {
            this.sparklineGrossInstance = renderSparkline(this.sparklineGrossRef, this.sparklineGrossInstance, this.sparklineData.gross_sales, this.sparklineData.labels, '#2ecc71');
            this.sparklineNetInstance = renderSparkline(this.sparklineNetRef, this.sparklineNetInstance, this.sparklineData.net_sales, this.sparklineData.labels, '#2ecc71');
            this.sparklineCostInstance = renderSparkline(this.sparklineCostRef, this.sparklineCostInstance, this.sparklineData.cost_of_sales, this.sparklineData.labels, '#2ecc71');
            this.sparklineProfitInstance = renderSparkline(this.sparklineProfitRef, this.sparklineProfitInstance, this.sparklineData.gross_profit, this.sparklineData.labels, '#2ecc71');
        }
    }
}

registry.category("actions").add("havano_dashboard_tag", HavanoDashboard);

