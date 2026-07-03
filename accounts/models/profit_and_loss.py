from odoo import models, fields, api
from datetime import datetime
from dateutil.relativedelta import relativedelta

class ProfitAndLossReport(models.AbstractModel):
    _name = 'havanoposdesk.profit.and.loss'
    _description = 'Profit and Loss Report Data'

    @api.model
    def get_report_data(self, date_from=None, date_to=None, store_ids=None, comparison='none'):
        domain_sale = [('state', '=', 'done')]
        domain_expense = [('state', '=', 'Posted')]
        
        comp_domain_sale = [('state', '=', 'done')]
        comp_domain_expense = [('state', '=', 'Posted')]

        if date_from:
            domain_sale.append(('date', '>=', date_from))
            domain_expense.append(('date', '>=', date_from))
        if date_to:
            domain_sale.append(('date', '<=', date_to))
            domain_expense.append(('date', '<=', date_to))

        has_comparison = comparison in ['previous_period', 'previous_year'] and date_from and date_to
        
        if has_comparison:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            
            if comparison == 'previous_year':
                comp_from = (dt_from - relativedelta(years=1)).strftime('%Y-%m-%d')
                comp_to = (dt_to - relativedelta(years=1)).strftime('%Y-%m-%d')
            else: # previous_period
                delta = dt_to - dt_from
                comp_to = (dt_from - relativedelta(days=1))
                comp_from = comp_to - delta
                comp_to = comp_to.strftime('%Y-%m-%d')
                comp_from = comp_from.strftime('%Y-%m-%d')
                
            comp_domain_sale.append(('date', '>=', comp_from))
            comp_domain_sale.append(('date', '<=', comp_to))
            comp_domain_expense.append(('date', '>=', comp_from))
            comp_domain_expense.append(('date', '<=', comp_to))

        # Stores to process
        stores = []
        if store_ids:
            store_records = self.env['havanoposdesk.store'].browse(store_ids)
            for st in store_records:
                if st.exists():
                    stores.append({'id': st.id, 'name': st.name})
        
        # Always add Total at the end
        stores.append({'id': 'total', 'name': 'Total'})

        # Setup dynamic columns based on comparison
        columns = []
        col_mappings = [] # To keep track of which mapping represents what
        
        for s in stores:
            if has_comparison:
                columns.extend([f"{s['name']}", f"{s['name']} (Prev)", f"{s['name']} (%)"])
                col_mappings.extend([
                    {'store': s['name'], 'type': 'current'},
                    {'store': s['name'], 'type': 'comparison'},
                    {'store': s['name'], 'type': 'percent'}
                ])
            else:
                columns.append(s['name'])
                col_mappings.append({'store': s['name'], 'type': 'current'})
        
        # Initialize data structure
        report_data = {
            'columns': columns,
            'revenue': {col: 0.0 for col in columns},
            'cost_of_revenue': {col: 0.0 for col in columns},
            'gross_profit': {col: 0.0 for col in columns},
            'expense_lines': {},
            'total_expenses': {col: 0.0 for col in columns},
            'net_profit': {col: 0.0 for col in columns},
        }
        
        def calculate_percent(current, previous):
            if previous == 0:
                return 100.0 if current > 0 else (0.0 if current == 0 else -100.0)
            return ((current - previous) / abs(previous)) * 100.0

        def process_records(domain, model, is_comparison=False):
            records = self.env[model].search(domain)
            for rec in records:
                if model == 'havanoposdesk.sale':
                    rev = rec.amount_total
                    cost = rec.total_cost
                    store_name = rec.store_id.name if rec.store_id and store_ids and rec.store_id.id in store_ids else None
                    
                    target_cols = []
                    if has_comparison:
                        target_cols.append(f"Total{' (Prev)' if is_comparison else ''}")
                        if store_name:
                            target_cols.append(f"{store_name}{' (Prev)' if is_comparison else ''}")
                    else:
                        target_cols.append("Total")
                        if store_name:
                            target_cols.append(store_name)
                            
                    for t in target_cols:
                        report_data['revenue'][t] += rev
                        report_data['cost_of_revenue'][t] += cost
                        
                elif model == 'havanoposdesk.expense':
                    account_name = rec.account_id.name if rec.account_id else 'Uncategorized'
                    amt = rec.amount
                    store_name = rec.store_id.name if rec.store_id and store_ids and rec.store_id.id in store_ids else None
                    
                    if account_name not in report_data['expense_lines']:
                        report_data['expense_lines'][account_name] = {col: 0.0 for col in columns}
                        
                    target_cols = []
                    if has_comparison:
                        target_cols.append(f"Total{' (Prev)' if is_comparison else ''}")
                        if store_name:
                            target_cols.append(f"{store_name}{' (Prev)' if is_comparison else ''}")
                    else:
                        target_cols.append("Total")
                        if store_name:
                            target_cols.append(store_name)
                            
                    for t in target_cols:
                        report_data['expense_lines'][account_name][t] += amt
                        report_data['total_expenses'][t] += amt

        # Process Current
        process_records(domain_sale, 'havanoposdesk.sale')
        process_records(domain_expense, 'havanoposdesk.expense')
        
        # Process Comparison
        if has_comparison:
            process_records(comp_domain_sale, 'havanoposdesk.sale', is_comparison=True)
            process_records(comp_domain_expense, 'havanoposdesk.expense', is_comparison=True)
            
            # Calculate percentages
            for s in stores:
                curr_col = s['name']
                prev_col = f"{s['name']} (Prev)"
                pct_col = f"{s['name']} (%)"
                
                report_data['revenue'][pct_col] = calculate_percent(report_data['revenue'][curr_col], report_data['revenue'][prev_col])
                report_data['cost_of_revenue'][pct_col] = calculate_percent(report_data['cost_of_revenue'][curr_col], report_data['cost_of_revenue'][prev_col])
                report_data['total_expenses'][pct_col] = calculate_percent(report_data['total_expenses'][curr_col], report_data['total_expenses'][prev_col])
                for acc in report_data['expense_lines']:
                    report_data['expense_lines'][acc][pct_col] = calculate_percent(report_data['expense_lines'][acc][curr_col], report_data['expense_lines'][acc][prev_col])

        # Format expense lines as a list for easier frontend iteration
        formatted_expense_lines = []
        for name, cols in report_data['expense_lines'].items():
            formatted_expense_lines.append({
                'name': name,
                'amounts': [cols[col] for col in columns],
                'total_sort': cols['Total'] if not has_comparison else cols['Total'] # Ensure sort relies on current total
            })
        
        # Sort by total amount descending
        formatted_expense_lines.sort(key=lambda x: x['total_sort'], reverse=True)
        report_data['expense_lines'] = formatted_expense_lines

        # Calculate Gross and Net Profits
        for col in columns:
            if has_comparison and col.endswith('(%)'):
                # Percentages are already calculated, just compute for Gross and Net by recalculating from the newly derived gross/net base values below
                pass
            else:
                report_data['gross_profit'][col] = report_data['revenue'][col] - report_data['cost_of_revenue'][col]
                report_data['net_profit'][col] = report_data['gross_profit'][col] - report_data['total_expenses'][col]
                
        if has_comparison:
            for s in stores:
                curr_col = s['name']
                prev_col = f"{s['name']} (Prev)"
                pct_col = f"{s['name']} (%)"
                report_data['gross_profit'][pct_col] = calculate_percent(report_data['gross_profit'][curr_col], report_data['gross_profit'][prev_col])
                report_data['net_profit'][pct_col] = calculate_percent(report_data['net_profit'][curr_col], report_data['net_profit'][prev_col])

        # Convert dictionaries to arrays ordered by columns for the frontend
        return {
            'columns': columns,
            'revenue': [report_data['revenue'][col] for col in columns],
            'cost_of_revenue': [report_data['cost_of_revenue'][col] for col in columns],
            'gross_profit': [report_data['gross_profit'][col] for col in columns],
            'expense_lines': formatted_expense_lines,
            'total_expenses': [report_data['total_expenses'][col] for col in columns],
            'net_profit': [report_data['net_profit'][col] for col in columns],
        }

    @api.model
    def get_available_stores(self):
        stores = self.env['havanoposdesk.store'].search_read([], ['id', 'name'])
        return stores
