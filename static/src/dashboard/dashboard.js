/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, useState, useRef, onWillUnmount } from "@odoo/owl";
import { loadJS, loadBundle } from "@web/core/assets";
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
                total_sales: 0,
                cost_of_sales: 0,
                gross_profit: 0,
                net_profit: 0,
                sales_trend: 0,
                cost_trend: 0,
                gross_profit_trend: 0,
                net_profit_trend: 0
            },
            stock_stats: {
                total_valuation: 0,
                total_items: 0
            },
            period: 'today',
            periodLabel: 'Today',
            customDateFrom: '',
            customDateTo: '',
            storeId: false,
            storeLabel: 'All Stores',
            stores: []
        });

        this.salesChartRef = useRef("salesChart");
        this.stockChartRef = useRef("stockChart");
        this.sparklineSalesRef = useRef("sparklineSales");
        this.sparklineCostRef = useRef("sparklineCost");
        this.sparklineGrossRef = useRef("sparklineGross");
        this.sparklineNetRef = useRef("sparklineNet");

        this.salesChartInstance = null;
        this.stockChartInstance = null;
        this.sparklineSalesInstance = null;
        this.sparklineCostInstance = null;
        this.sparklineGrossInstance = null;
        this.sparklineNetInstance = null;

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            this.state.stores = await this.orm.searchRead("havanoposdesk.store", [], ["id", "name"]);
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
            if (this.sparklineSalesInstance) this.sparklineSalesInstance.destroy();
            if (this.sparklineCostInstance) this.sparklineCostInstance.destroy();
            if (this.sparklineGrossInstance) this.sparklineGrossInstance.destroy();
            if (this.sparklineNetInstance) this.sparklineNetInstance.destroy();
        });
    }
    
    getAspectRatio() {
        const width = window.innerWidth;
        if (width < 576) return 1.5;
        if (width < 992) return 2;
        return 3;
    }

    onResize = () => {
        const ratio = this.getAspectRatio();
        if (this.salesChartInstance) {
            this.salesChartInstance.options.aspectRatio = ratio;
            this.salesChartInstance.resize();
        }
        if (this.stockChartInstance) {
            this.stockChartInstance.options.aspectRatio = ratio;
            this.stockChartInstance.resize();
        }
        if (this.sparklineSalesInstance) this.sparklineSalesInstance.resize();
        if (this.sparklineCostInstance) this.sparklineCostInstance.resize();
        if (this.sparklineGrossInstance) this.sparklineGrossInstance.resize();
        if (this.sparklineNetInstance) this.sparklineNetInstance.resize();
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
            [date_from, date_to, this.state.storeId]
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

    async setStore(storeId, label) {
        this.state.storeId = storeId;
        this.state.storeLabel = label;
        await this.fetchData();
        this.renderCharts();
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
        const ratio = this.getAspectRatio();
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
                            label: 'Net profit',
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
                            label: 'Gross profit',
                            data: this.salesChartData.gross_sales,
                            backgroundColor: '#3498db',
                            borderRadius: 4,
                            maxBarThickness: 50
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    aspectRatio: ratio,
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
                    maintainAspectRatio: true,
                    aspectRatio: ratio,
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
            this.sparklineSalesInstance = renderSparkline(this.sparklineSalesRef, this.sparklineSalesInstance, this.sparklineData.total_sales || this.sparklineData.gross_sales, this.sparklineData.labels, '#2ecc71');
            this.sparklineCostInstance = renderSparkline(this.sparklineCostRef, this.sparklineCostInstance, this.sparklineData.cost_of_sales, this.sparklineData.labels, '#e67e22');
            this.sparklineGrossInstance = renderSparkline(this.sparklineGrossRef, this.sparklineGrossInstance, this.sparklineData.gross_profit, this.sparklineData.labels, '#1abc9c');
            this.sparklineNetInstance = renderSparkline(this.sparklineNetRef, this.sparklineNetInstance, this.sparklineData.net_profit || this.sparklineData.gross_profit, this.sparklineData.labels, '#f1c40f');
        }
    }
}

registry.category("actions").add("havano_dashboard_tag", HavanoDashboard, { force: true });

export class TenantMonitoringDashboard extends Component {
    static template = "havanoposdesk_odoo.TenantMonitoringDashboard";
    static components = { Dropdown, DropdownItem };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            tenantId: false,
            tenantLabel: "All Tenants (Aggregated)",
            tenants: [],
            selectedTenants: [],   // array of selected tenant IDs
            tenantSearch: "",      // search filter string
            tenantDropdownOpen: false,
            period: "this_month",
            periodLabel: "This month",
            isLoading: false,
            kpis: {
                sales: { total_amount: 0, transactions_count: 0 },
                purchases: { total_amount: 0, transactions_count: 0 },
                stock_adjustments: { operations_count: 0, total_valuation_diff: 0 },
                activity: { total_events: 0 }
            }
        });

        this.trendCanvasRef = useRef("salesChartCanvas");
        this.distributionCanvasRef = useRef("distributionChartCanvas");
        this.purchaseCanvasRef = useRef("purchaseChartCanvas");
        this.breakdownCanvasRef = useRef("breakdownChartCanvas");

        this.trendChart = null;
        this.distributionChart = null;
        this.purchaseChart = null;
        this.breakdownChart = null;

        this.chartData = null;

        onWillStart(async () => {
            if (!document.getElementById("google-font-jakarta")) {
                const link = document.createElement("link");
                link.id = "google-font-jakarta";
                link.rel = "stylesheet";
                link.href = "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap";
                document.head.appendChild(link);
            }
            try {
                await loadJS("/web/static/lib/Chart/Chart.js");
            } catch (e) {
                console.warn("Chart.js load warning:", e);
            }
            await this.fetchData();
        });

        onMounted(() => {
            this.renderAllCharts();
            this.onResize = () => this.resizeCharts();
            window.addEventListener("resize", this.onResize);
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this.onResize);
            this.destroyCharts();
        });
    }

    formatCurrency(value) {
        if (value === undefined || value === null) return "0.00";
        return Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    getDateRange() {
        const now = new Date();
        const formatDate = (date) => {
            const d = new Date(date);
            let month = "" + (d.getMonth() + 1);
            let day = "" + d.getDate();
            const year = d.getFullYear();
            if (month.length < 2) month = "0" + month;
            if (day.length < 2) day = "0" + day;
            return [year, month, day].join("-");
        };

        let dateFrom = formatDate(now);
        let dateTo = formatDate(now);

        if (this.state.period === "today") {
            dateFrom = formatDate(now);
            dateTo = formatDate(now);
        } else if (this.state.period === "yesterday") {
            const y = new Date(now);
            y.setDate(now.getDate() - 1);
            dateFrom = formatDate(y);
            dateTo = formatDate(y);
        } else if (this.state.period === "this_week") {
            const current = new Date();
            const day = current.getDay();
            const diff = current.getDate() - day + (day === 0 ? -6 : 1);
            const monday = new Date(current.setDate(diff));
            const sunday = new Date(monday);
            sunday.setDate(monday.getDate() + 6);
            dateFrom = formatDate(monday);
            dateTo = formatDate(sunday);
        } else if (this.state.period === "last_week") {
            const current = new Date();
            const day = current.getDay();
            const diff = current.getDate() - day + (day === 0 ? -6 : 1) - 1;
            const endLastWeek = new Date(current.setDate(diff));
            const startLastWeek = new Date(endLastWeek);
            startLastWeek.setDate(endLastWeek.getDate() - 6);
            dateFrom = formatDate(startLastWeek);
            dateTo = formatDate(endLastWeek);
        } else if (this.state.period === "this_month") {
            const m = new Date(now.getFullYear(), now.getMonth(), 1);
            const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0);
            dateFrom = formatDate(m);
            dateTo = formatDate(endOfMonth);
        } else if (this.state.period === "all") {
            dateFrom = `${now.getFullYear() - 1}-01-01`;
            dateTo = formatDate(now);
        }

        return { dateFrom, dateTo };
    }

    async fetchData() {
        this.state.isLoading = true;
        try {
            const { dateFrom, dateTo } = this.getDateRange();
            let granularity = "weekly";
            if (this.state.period === "today" || this.state.period === "yesterday" || this.state.period === "this_week" || this.state.period === "last_week") {
                granularity = "daily";
            } else if (this.state.period === "this_month") {
                granularity = "daily";
            } else if (this.state.period === "all") {
                granularity = "monthly";
            }

            const res = await this.orm.call(
                "havanoposdesk.tenant.analytics",
                "get_dashboard_data",
                [],
                {
                    tenant_id: this.state.tenantId,
                    date_from: dateFrom,
                    date_to: dateTo,
                    granularity: granularity
                }
            );

            if (res) {
                if (res.tenants) {
                    this.state.tenants = res.tenants;
                }
                if (res.kpis) {
                    Object.assign(this.state.kpis, res.kpis);
                }
                this.chartData = res;
            }
        } catch (e) {
            console.error("Failed to load monitoring dashboard data:", e);
        } finally {
            this.state.isLoading = false;
        }
    }

    // ── Multi-select tenant helpers ────────────────────────────────────────────

    get filteredTenants() {
        const q = (this.state.tenantSearch || "").toLowerCase().trim();
        if (!q) return this.state.tenants;
        return this.state.tenants.filter(t => t.name.toLowerCase().includes(q));
    }

    get tenantFilterLabel() {
        const sel = this.state.selectedTenants;
        if (!sel || sel.length === 0) return "All Tenants (Aggregated)";
        if (sel.length === 1) {
            const t = this.state.tenants.find(x => x.id === sel[0]);
            return t ? t.name : "1 Tenant";
        }
        return `${sel.length} Tenants Selected`;
    }

    toggleTenantDropdown(ev) {
        ev.stopPropagation();
        this.state.tenantDropdownOpen = !this.state.tenantDropdownOpen;
        if (this.state.tenantDropdownOpen) {
            const handler = (e) => {
                if (!e.target.closest('.tenant-multiselect-panel') && !e.target.closest('.tenant-multiselect-wrapper > button')) {
                    this.state.tenantDropdownOpen = false;
                    document.removeEventListener("click", handler);
                }
            };
            setTimeout(() => document.addEventListener("click", handler), 0);
        }
    }

    async toggleTenant(tenantId) {
        const idx = this.state.selectedTenants.indexOf(tenantId);
        if (idx === -1) {
            this.state.selectedTenants.push(tenantId);
        } else {
            this.state.selectedTenants.splice(idx, 1);
        }
        await this._applyTenantFilter();
    }

    async selectAllTenants() {
        this.state.selectedTenants = [];
        this.state.tenantDropdownOpen = false;
        await this._applyTenantFilter();
    }

    onTenantSearch() {
        // reactive — state.tenantSearch updated by t-model
    }

    async _applyTenantFilter() {
        if (this.state.selectedTenants.length > 0) {
            this.state.tenantId = this.state.selectedTenants.length === 1 
                ? this.state.selectedTenants[0] 
                : this.state.selectedTenants;
        } else {
            this.state.tenantId = false;
        }
        await this.fetchData();
        this.renderAllCharts();
    }

    async onTenantFilterChange(ev) {
        const val = ev.target.value;
        const tenantId = val === "all" ? false : parseInt(val);
        const selected = this.state.tenants.find(t => t.id === tenantId);
        const label = selected ? selected.name : "All Tenants (Aggregated)";
        await this.setTenant(tenantId, label);
    }

    async setTenant(tenantId, label) {
        this.state.tenantId = tenantId;
        this.state.tenantLabel = label;
        await this.fetchData();
        this.renderAllCharts();
    }

    async setPeriod(period, label) {
        this.state.period = period;
        this.state.periodLabel = label;
        await this.fetchData();
        this.renderAllCharts();
    }

    async refreshData() {
        await this.fetchData();
        this.renderAllCharts();
    }

    destroyCharts() {
        if (this.trendChart) { this.trendChart.destroy(); this.trendChart = null; }
        if (this.distributionChart) { this.distributionChart.destroy(); this.distributionChart = null; }
        if (this.purchaseChart) { this.purchaseChart.destroy(); this.purchaseChart = null; }
        if (this.breakdownChart) { this.breakdownChart.destroy(); this.breakdownChart = null; }
    }

    resizeCharts() {
        if (this.trendChart) this.trendChart.resize();
        if (this.distributionChart) this.distributionChart.resize();
        if (this.purchaseChart) this.purchaseChart.resize();
        if (this.breakdownChart) this.breakdownChart.resize();
    }

    renderAllCharts() {
        if (!this.chartData || typeof window.Chart === "undefined") return;
        this.destroyCharts();

        this.renderSalesTrendChart();
        this.renderDistributionChart();
        this.renderPurchasesChart();
        this.renderBreakdownChart();
    }

    renderSalesTrendChart() {
        const canvas = this.trendCanvasRef.el;
        if (!canvas || !this.chartData.sales_chart) return;
        const salesData = this.chartData.sales_chart;
        const ctx = canvas.getContext("2d");

        // Havano subtle gradient under sales revenue line
        const gradient = ctx.createLinearGradient(0, 0, 0, 260);
        gradient.addColorStop(0, "rgba(0, 128, 255, 0.22)");
        gradient.addColorStop(1, "rgba(0, 128, 255, 0.0)");

        this.trendChart = new window.Chart(canvas, {
            type: "line",
            data: {
                labels: salesData.labels,
                datasets: [
                    {
                        label: "Gross Revenue ($)",
                        data: salesData.amounts,
                        borderColor: "#0080ff",
                        backgroundColor: gradient,
                        fill: true,
                        tension: 0.35,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        pointBackgroundColor: "#0080ff",
                        borderWidth: 2.5,
                        yAxisID: "y",
                    },
                    {
                        label: "Invoices / Transactions",
                        data: salesData.counts,
                        borderColor: "#64748b",
                        backgroundColor: "transparent",
                        borderDash: [4, 4],
                        tension: 0.35,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        pointBackgroundColor: "#64748b",
                        borderWidth: 1.8,
                        yAxisID: "y1",
                    }
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: "index",
                    intersect: false,
                },
                plugins: {
                    legend: {
                        display: true,
                        position: "top",
                        align: "end",
                        labels: { boxWidth: 12, usePointStyle: true, pointStyle: "circle", font: { family: "'Plus Jakarta Sans', sans-serif", size: 12, weight: 600 } },
                    },
                    tooltip: {
                        backgroundColor: "#0f172a",
                        titleColor: "#ffffff",
                        bodyColor: "#f1f5f9",
                        titleFont: { family: "'Plus Jakarta Sans', sans-serif" },
                        bodyFont: { family: "'Plus Jakarta Sans', sans-serif" },
                        padding: 10,
                        cornerRadius: 8,
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 }, autoSkip: true, maxTicksLimit: 10 },
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: "rgba(0, 0, 0, 0.05)" },
                        ticks: { font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } },
                    },
                    y1: {
                        beginAtZero: true,
                        position: "right",
                        grid: { display: false },
                        ticks: { precision: 0, font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } },
                    }
                },
            },
        });
    }

    renderDistributionChart() {
        const canvas = this.distributionCanvasRef.el;
        if (!canvas) return;
        const distData = this.chartData.distribution_chart || {
            labels: ["Sales Invoices", "Purchase Orders", "Stock Adjustments"],
            data: [
                this.state.kpis.sales?.transactions_count || 0,
                this.state.kpis.purchases?.transactions_count || 0,
                this.state.kpis.stock_adjustments?.operations_count || 0,
            ],
            colors: ["#0080ff", "#38bdf8", "#94a3b8"],
        };
        if (!distData || !distData.labels) return;

        this.distributionChart = new window.Chart(canvas, {
            type: "doughnut",
            data: {
                labels: distData.labels,
                datasets: [
                    {
                        data: distData.data,
                        backgroundColor: distData.colors || ["#0080ff", "#38bdf8", "#94a3b8"],
                        borderWidth: 2,
                        borderColor: "#ffffff",
                        hoverOffset: 6,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "68%",
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            boxWidth: 12,
                            padding: 12,
                            usePointStyle: true,
                            pointStyle: "circle",
                            font: { family: "'Plus Jakarta Sans', sans-serif", size: 12, weight: 600 },
                        },
                    },
                    tooltip: {
                        backgroundColor: "#0f172a",
                        titleColor: "#ffffff",
                        bodyColor: "#f1f5f9",
                        titleFont: { family: "'Plus Jakarta Sans', sans-serif" },
                        bodyFont: { family: "'Plus Jakarta Sans', sans-serif" },
                        padding: 10,
                        cornerRadius: 8,
                        callbacks: {
                            label: function (context) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const val = context.raw || 0;
                                const pct = total > 0 ? Math.round((val / total) * 100) : 0;
                                return ` ${context.label}: ${val.toLocaleString()} (${pct}%)`;
                            },
                        },
                    },
                },
            },
        });
    }

    renderPurchasesChart() {
        const canvas = this.purchaseCanvasRef.el;
        if (!canvas || !this.chartData.purchase_chart) return;
        const purchaseData = this.chartData.purchase_chart;
        const ctx = canvas.getContext("2d");

        // Subtle Havano cyan/blue gradient for procurement
        const gradient = ctx.createLinearGradient(0, 0, 0, 240);
        gradient.addColorStop(0, "rgba(2, 132, 199, 0.22)");
        gradient.addColorStop(1, "rgba(2, 132, 199, 0.0)");

        this.purchaseChart = new window.Chart(canvas, {
            type: "line",
            data: {
                labels: purchaseData.labels,
                datasets: [
                    {
                        label: "Procurement Spend ($)",
                        data: purchaseData.amounts,
                        borderColor: "#0284c7",
                        backgroundColor: gradient,
                        fill: true,
                        tension: 0.35,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        pointBackgroundColor: "#0284c7",
                        borderWidth: 2.5,
                        yAxisID: "y",
                    },
                    {
                        label: "PO Records",
                        data: purchaseData.counts,
                        borderColor: "#64748b",
                        backgroundColor: "transparent",
                        borderDash: [4, 4],
                        tension: 0.35,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        pointBackgroundColor: "#64748b",
                        borderWidth: 1.8,
                        yAxisID: "y1",
                    }
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: "index",
                    intersect: false,
                },
                plugins: {
                    legend: {
                        position: "top",
                        align: "end",
                        labels: { boxWidth: 12, usePointStyle: true, pointStyle: "circle", font: { family: "'Plus Jakarta Sans', sans-serif", size: 12, weight: 600 } },
                    },
                    tooltip: {
                        backgroundColor: "#0f172a",
                        titleColor: "#ffffff",
                        bodyColor: "#f1f5f9",
                        titleFont: { family: "'Plus Jakarta Sans', sans-serif" },
                        bodyFont: { family: "'Plus Jakarta Sans', sans-serif" },
                        padding: 10,
                        cornerRadius: 8,
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 }, autoSkip: true, maxTicksLimit: 10 },
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: "rgba(0, 0, 0, 0.05)" },
                        ticks: { font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } },
                    },
                    y1: {
                        beginAtZero: true,
                        position: "right",
                        grid: { display: false },
                        ticks: { precision: 0, font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } },
                    }
                },
            },
        });
    }

    renderBreakdownChart() {
        const canvas = this.breakdownCanvasRef.el;
        if (!canvas) return;
        const bData = this.chartData.breakdown_chart || {
            labels: ["Positive Adj (Stock In)", "Negative Adj (Stock Out)", "Purchase Orders", "Sales Invoices"],
            data: [
                Math.round(this.state.kpis.stock_adjustments?.positive_qty || 0),
                Math.round(this.state.kpis.stock_adjustments?.negative_qty || 0),
                this.state.kpis.purchases?.transactions_count || 0,
                this.state.kpis.sales?.transactions_count || 0,
            ],
            colors: ["#0080ff", "#38bdf8", "#64748b", "#cbd5e1"],
        };
        if (!bData || !bData.labels) return;

        this.breakdownChart = new window.Chart(canvas, {
            type: "bar",
            data: {
                labels: bData.labels,
                datasets: [
                    {
                        label: "Operations Count",
                        data: bData.data,
                        backgroundColor: bData.colors || ["#0080ff", "#38bdf8", "#64748b", "#cbd5e1"],
                        borderRadius: 5,
                    },
                ],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        beginAtZero: true,
                        grid: { color: "rgba(0, 0, 0, 0.05)" },
                        ticks: { precision: 0, font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } },
                    },
                    y: {
                        grid: { display: false },
                        ticks: { font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } },
                    },
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "#0f172a",
                        titleColor: "#ffffff",
                        bodyColor: "#f1f5f9",
                        titleFont: { family: "'Plus Jakarta Sans', sans-serif" },
                        bodyFont: { family: "'Plus Jakarta Sans', sans-serif" },
                        padding: 10,
                        cornerRadius: 8,
                    },
                },
            },
        });
    }
}

registry.category("actions").add("havanoposdesk.tenant_analytics", TenantMonitoringDashboard, { force: true });


