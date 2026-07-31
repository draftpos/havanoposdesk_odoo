from odoo import models, fields, api
from datetime import datetime, timedelta
import pytz

class HavanoposdeskDashboard(models.AbstractModel):
    _name = 'havanoposdesk.dashboard'
    _description = 'Dashboard Model'

    @api.model
    def get_dashboard_data(self, date_from, date_to):
        """
        Fetch KPI and Chart data for the dashboard.
        """
        tenant_id = self.env.user.tenant_id.id
        domain_sale = [('tenant_id', '=', tenant_id)] if tenant_id else []
        domain_val = [('tenant_id', '=', tenant_id)] if tenant_id else []
        
        # Calculate previous period for trends
        prev_domain_sale = list(domain_sale)
        if date_from and date_to:
            start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
            end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
            diff_days = (end_date - start_date).days + 1
            prev_start = start_date - timedelta(days=diff_days)
            prev_end = end_date - timedelta(days=diff_days)
            
            start = f"{date_from} 00:00:00"
            end = f"{date_to} 23:59:59"
            domain_sale += [('date', '>=', start), ('date', '<=', end)]
            
            p_start = f"{prev_start} 00:00:00"
            p_end = f"{prev_end} 23:59:59"
            prev_domain_sale += [('date', '>=', p_start), ('date', '<=', p_end)]

        # Domain for expenses
        domain_exp = [('tenant_id', '=', tenant_id)] if tenant_id else []
        prev_domain_exp = list(domain_exp)

        if date_from and date_to:
            domain_exp += [('date', '>=', date_from), ('date', '<=', date_to)]
            prev_domain_exp += [('date', '>=', prev_start), ('date', '<=', prev_end)]

        # Fetch current period data
        sales = self.env['havanoposdesk.sale'].search(domain_sale)
        expenses = self.env['havanoposdesk.expense'].search(domain_exp + [('state', '=', 'Posted')])
        
        # Fetch previous period data
        prev_sales = self.env['havanoposdesk.sale'].search(prev_domain_sale)
        prev_expenses = self.env['havanoposdesk.expense'].search(prev_domain_exp + [('state', '=', 'Posted')])

        def compute_kpis(sales_records, expense_records):
            ts = sum(s.amount_total or 0.0 for s in sales_records)
            cs = sum(s.total_cost or 0.0 for s in sales_records)
            gp = ts - cs
            ex = sum(e.amount or 0.0 for e in expense_records)
            np = gp - ex
            return ts, cs, gp, np, ex

        def compute_trend(curr, prev):
            if not prev:
                return 100.0 if curr > 0 else 0.0
            return round(((curr - prev) / abs(prev)) * 100, 1)

        total_sales, cost_of_sales, gross_profit, net_profit, total_expenses = compute_kpis(sales, expenses)
        prev_sales_val, prev_cost, prev_gross, prev_net, prev_exp = compute_kpis(prev_sales, prev_expenses)

        sales_trend = compute_trend(total_sales, prev_sales_val)
        cost_trend = compute_trend(cost_of_sales, prev_cost)
        gross_profit_trend = compute_trend(gross_profit, prev_gross)
        net_profit_trend = compute_trend(net_profit, prev_net)

        daily_sales_data = {}

        for sale in sales:
            gross = sale.amount_total or 0.0
            net = sale.amount_untaxed or 0.0
            cost = sale.total_cost or 0.0
            profit = gross - cost
            
            # Daily grouping
            day = sale.date.strftime('%Y-%m-%d') if sale.date else 'Unknown'
            if day not in daily_sales_data:
                daily_sales_data[day] = {
                    'gross_sales': 0,
                    'net_sales': 0,
                    'cost_of_sales': 0,
                    'gross_profit': 0
                }
            
            daily_sales_data[day]['gross_sales'] += gross
            daily_sales_data[day]['net_sales'] += net
            daily_sales_data[day]['cost_of_sales'] += cost
            daily_sales_data[day]['gross_profit'] += profit

        # Format Sales Data for Chart.js
        sorted_days = sorted(daily_sales_data.keys())
        sales_summary_chart = {
            'labels': sorted_days,
            'gross_sales': [daily_sales_data[d]['gross_sales'] for d in sorted_days],
            'net_sales': [daily_sales_data[d]['net_sales'] for d in sorted_days],
            'cost_of_sales': [daily_sales_data[d]['cost_of_sales'] for d in sorted_days],
            'gross_profit': [daily_sales_data[d]['gross_profit'] for d in sorted_days],
        }

        # Sparkline Data (Individual Transactions)
        sorted_sales = sorted(sales, key=lambda s: s.date) if sales else []
        sparkline_data = {
            'labels': [s.date.strftime('%H:%M') for s in sorted_sales],
            'total_sales': [s.amount_total or 0.0 for s in sorted_sales],
            'cost_of_sales': [s.total_cost or 0.0 for s in sorted_sales],
            'gross_profit': [(s.amount_total or 0.0) - (s.total_cost or 0.0) for s in sorted_sales],
            'net_profit': [(s.amount_total or 0.0) - (s.total_cost or 0.0) for s in sorted_sales],
        }

        # Stock Valuation
        valuations = self.env['havanoposdesk.stock.valuation'].sudo().search(domain_val)
        valuation_data = {}
        total_valuation = 0.0
        total_items = 0.0

        for val in valuations:
            cat = val.product_id.category_id.name if val.product_id.category_id else 'Uncategorized'
            if cat not in valuation_data:
                valuation_data[cat] = 0.0
            
            value = val.value_cost or 0.0
            valuation_data[cat] += value
            total_valuation += value
            total_items += val.on_hand_qty or 0.0

        sorted_cats = sorted(valuation_data.keys())
        stock_valuation_chart = {
            'labels': sorted_cats,
            'valuation': [valuation_data[c] for c in sorted_cats]
        }

        return {
            'kpis': {
                'total_sales': total_sales,
                'cost_of_sales': cost_of_sales,
                'gross_profit': gross_profit,
                'net_profit': net_profit,
                'total_expenses': total_expenses,
                'sales_trend': sales_trend,
                'cost_trend': cost_trend,
                'gross_profit_trend': gross_profit_trend,
                'net_profit_trend': net_profit_trend,
                # Keep gross_sales and net_sales for backwards compat if referenced anywhere
                'gross_sales': total_sales,
                'net_sales': total_sales,
                'gross_trend': sales_trend,
                'net_trend': sales_trend,
                'profit_trend': gross_profit_trend
            },
            'stock_stats': {
                'total_valuation': total_valuation,
                'total_items': total_items,
            },
            'sales_chart': sales_summary_chart,
            'sparkline_data': sparkline_data,
            'stock_chart': stock_valuation_chart,
        }
