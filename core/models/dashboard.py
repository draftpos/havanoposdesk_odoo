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
        if not tenant_id:
            return {}

        domain_sale = [('tenant_id', '=', tenant_id)]
        domain_val = [('tenant_id', '=', tenant_id)]
        
        if date_from and date_to:
            # Add time to capture the entire day
            start = f"{date_from} 00:00:00"
            end = f"{date_to} 23:59:59"
            domain_sale += [('date', '>=', start), ('date', '<=', end)]

        sales = self.env['havanoposdesk.sale'].search(domain_sale)
        
        gross_sales = 0.0
        net_sales = 0.0
        cost_of_sales = 0.0
        gross_profit = 0.0
        
        daily_sales_data = {}

        for sale in sales:
            gross = sale.amount_total
            net = sale.amount_total - (sale.discount_amount or 0.0) # Assume discount if applicable
            cost = sum(line.product_id.buying_price * line.qty for line in sale.line_ids if line.product_id)
            profit = net - cost
            
            gross_sales += gross
            net_sales += net
            cost_of_sales += cost
            gross_profit += profit

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

        # Stock Valuation
        valuations = self.env['havanoposdesk.stock.valuation'].search(domain_val)
        
        # Here we just want a summary of valuation. Since stock valuation isn't usually a time-series 
        # unless logged daily, we will group by Product Category to show in a bar chart or line chart 
        # as requested, OR just show a single point. If they want a time-series of valuation, we might 
        # need to use stock ledgers or just show current valuation per category.
        # Let's show current stock valuation grouped by Product Category.
        valuation_data = {}
        for val in valuations:
            cat = val.product_id.category_id.name if val.product_id.category_id else 'Uncategorized'
            if cat not in valuation_data:
                valuation_data[cat] = 0.0
            valuation_data[cat] += val.value_cost

        sorted_cats = sorted(valuation_data.keys())
        stock_valuation_chart = {
            'labels': sorted_cats,
            'valuation': [valuation_data[c] for c in sorted_cats]
        }

        return {
            'kpis': {
                'gross_sales': gross_sales,
                'net_sales': net_sales,
                'cost_of_sales': cost_of_sales,
                'gross_profit': gross_profit,
            },
            'sales_chart': sales_summary_chart,
            'stock_chart': stock_valuation_chart,
        }
