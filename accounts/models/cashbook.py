# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime
from dateutil.relativedelta import relativedelta
import io
import xlsxwriter

class CashbookReport(models.AbstractModel):
    _name = 'havanoposdesk.cashbook'
    _description = 'Cashbook Report Data'

    def _get_active_tenant_id(self):
        user = self.env.user
        tenant = user.tenant_id
        if not tenant and user.havano_role != 'super_admin' and user.company_id:
            tenant = self.env['havanoposdesk.tenant'].sudo().search([('id', '=', user.company_id.id)], limit=1)
        return tenant.id if tenant else False

    @api.model
    def get_available_stores(self):
        tenant_id = self._get_active_tenant_id()
        if tenant_id:
            domain = [('tenant_id', '=', tenant_id)]
        elif self.env.user.havano_role == 'super_admin':
            domain = []
        else:
            return []
            
        stores = self.env['havanoposdesk.store'].sudo().search_read(domain, ['id', 'name'])
        return stores

    @api.model
    def get_available_accounts(self):
        tenant_id = self._get_active_tenant_id()
        if tenant_id:
            domain = [('tenant_id', '=', tenant_id)]
        elif self.env.user.havano_role == 'super_admin':
            domain = []
        else:
            return []
            
        accounts = self.env['havanoposdesk.account'].sudo().search_read(domain, ['id', 'name', 'type', 'balance'])
        return accounts

    @api.model
    def get_report_data(self, date_from=None, date_to=None, store_ids=None, comparison='none', account_ids=None):
        user = self.env.user
        tenant_id = self._get_active_tenant_id()
        user_tenant = self.env['havanoposdesk.tenant'].sudo().browse(tenant_id) if tenant_id else False

        # Multi-tenant safety barrier: non-super_admin without tenant cannot access records
        if not tenant_id and user.havano_role != 'super_admin':
            return {
                'columns': ['Total'],
                'currency_symbol': '$',
                'opening_balance': [0.0],
                'sales': [0.0],
                'customer_receipts': [0.0],
                'transfers_in': [0.0],
                'total_inflows': [0.0],
                'expenses': [0.0],
                'expense_lines': [],
                'transfers_out': [0.0],
                'supplier_payments': [0.0],
                'total_outflows': [0.0],
                'net_movement': [0.0],
                'closing_balance': [0.0],
                'accounts': [],
            }

        domain_sale = [('state', '!=', 'cancelled')]
        domain_expense = [('state', 'not in', ['cancelled', 'Cancelled']), ('is_paid', '=', True)]
        domain_payment = [('state', '!=', 'cancelled')]
        domain_transfer = [('state', 'not in', ['cancelled', 'Cancelled'])]

        comp_domain_sale = [('state', '!=', 'cancelled')]
        comp_domain_expense = [('state', 'not in', ['cancelled', 'Cancelled']), ('is_paid', '=', True)]
        comp_domain_payment = [('state', '!=', 'cancelled')]
        comp_domain_transfer = [('state', 'not in', ['cancelled', 'Cancelled'])]

        if date_from:
            domain_sale.append(('date', '>=', date_from))
            domain_expense.append(('date', '>=', date_from))
            domain_payment.append(('date', '>=', date_from))
            domain_transfer.append(('date', '>=', date_from))
        if date_to:
            domain_sale.append(('date', '<=', date_to))
            domain_expense.append(('date', '<=', date_to))
            domain_payment.append(('date', '<=', date_to))
            domain_transfer.append(('date', '<=', date_to))

        has_comparison = comparison in ['previous_period', 'previous_year'] and date_from and date_to

        if has_comparison:
            dt_from = datetime.strptime(date_from[:10], '%Y-%m-%d')
            dt_to = datetime.strptime(date_to[:10], '%Y-%m-%d')

            if comparison == 'previous_year':
                comp_from = (dt_from - relativedelta(years=1)).strftime('%Y-%m-%d')
                comp_to = (dt_to - relativedelta(years=1)).strftime('%Y-%m-%d')
            else:
                delta = dt_to - dt_from
                comp_to_dt = (dt_from - relativedelta(days=1))
                comp_from_dt = comp_to_dt - delta
                comp_to = comp_to_dt.strftime('%Y-%m-%d')
                comp_from = comp_from_dt.strftime('%Y-%m-%d')

            comp_domain_sale.append(('date', '>=', comp_from))
            comp_domain_sale.append(('date', '<=', comp_to))
            comp_domain_expense.append(('date', '>=', comp_from))
            comp_domain_expense.append(('date', '<=', comp_to))
            comp_domain_payment.append(('date', '>=', comp_from))
            comp_domain_payment.append(('date', '<=', comp_to))
            comp_domain_transfer.append(('date', '>=', comp_from))
            comp_domain_transfer.append(('date', '<=', comp_to))

        # Stores to process (Strict tenant filtering)
        stores = []
        if store_ids:
            domain_st = [('id', 'in', store_ids)]
            if tenant_id:
                domain_st.append(('tenant_id', '=', tenant_id))
            store_records = self.env['havanoposdesk.store'].sudo().search(domain_st)
            for st in store_records:
                stores.append({'id': st.id, 'name': st.name})
        else:
            domain_st = [('tenant_id', '=', tenant_id)] if tenant_id else []
            all_st = self.env['havanoposdesk.store'].sudo().search(domain_st)
            for st in all_st:
                stores.append({'id': st.id, 'name': st.name})

        # Always add Total at the end
        stores.append({'id': 'total', 'name': 'Total'})

        # Setup dynamic columns based on comparison (matching P&L)
        columns = []
        for s in stores:
            if has_comparison:
                columns.extend([f"{s['name']}", f"{s['name']} (Prev)", f"{s['name']} (%)"])
            else:
                columns.append(s['name'])

        # Initialize data structures matching P&L format
        report_data = {
            'columns': columns,
            'opening_balance': {col: 0.0 for col in columns},
            'sales': {col: 0.0 for col in columns},
            'customer_receipts': {col: 0.0 for col in columns},
            'transfers_in': {col: 0.0 for col in columns},
            'total_inflows': {col: 0.0 for col in columns},
            'expenses': {col: 0.0 for col in columns},
            'expense_lines': {},
            'transfers_out': {col: 0.0 for col in columns},
            'supplier_payments': {col: 0.0 for col in columns},
            'total_outflows': {col: 0.0 for col in columns},
            'net_movement': {col: 0.0 for col in columns},
            'closing_balance': {col: 0.0 for col in columns},
            'accounts': [],
            'currency_symbol': '$'
        }

        if user_tenant and user_tenant.currency_id and user_tenant.currency_id.symbol:
            report_data['currency_symbol'] = user_tenant.currency_id.symbol

        # Helper to compute opening balance prior to date_from
        if date_from:
            prior_sale_domain = [('state', '!=', 'cancelled'), ('date', '<', date_from)]
            prior_exp_domain = [('state', 'not in', ['cancelled', 'Cancelled']), ('is_paid', '=', True), ('date', '<', date_from)]
            prior_pay_domain = [('state', '!=', 'cancelled'), ('date', '<', date_from)]
            prior_trans_domain = [('state', 'not in', ['cancelled', 'Cancelled']), ('date', '<', date_from)]

            if tenant_id:
                prior_sale_domain.append(('tenant_id', '=', tenant_id))
                prior_exp_domain.append(('tenant_id', '=', tenant_id))
                prior_pay_domain.append(('tenant_id', '=', tenant_id))
                prior_trans_domain.append(('tenant_id', '=', tenant_id))
            elif user.havano_role != 'super_admin':
                prior_sale_domain.append(('id', '=', 0))
                prior_exp_domain.append(('id', '=', 0))
                prior_pay_domain.append(('id', '=', 0))
                prior_trans_domain.append(('id', '=', 0))

            for s in self.env['havanoposdesk.sale'].sudo().search(prior_sale_domain):
                amt = s.amount_total or 0.0
                st_name = s.store_id.name if s.store_id else None
                if st_name and st_name in report_data['opening_balance']:
                    report_data['opening_balance'][st_name] += amt
                report_data['opening_balance']['Total'] += amt

            for e in self.env['havanoposdesk.expense'].sudo().search(prior_exp_domain):
                amt = e.amount or 0.0
                st_name = e.store_id.name if e.store_id else None
                if st_name and st_name in report_data['opening_balance']:
                    report_data['opening_balance'][st_name] -= amt
                report_data['opening_balance']['Total'] -= amt

            for p in self.env['havanoposdesk.payment'].sudo().search(prior_pay_domain):
                if p.pos_sale_ids or (p.sale_id and p.sale_id.state in ['done', 'confirmed']):
                    continue
                amt = p.amount or 0.0
                is_in = (p.payment_type == 'receipt')
                st_name = p.store_id.name if p.store_id else None
                if st_name and st_name in report_data['opening_balance']:
                    report_data['opening_balance'][st_name] += (amt if is_in else -amt)
                report_data['opening_balance']['Total'] += (amt if is_in else -amt)

            for t in self.env['havanoposdesk.cash.transfer'].sudo().search(prior_trans_domain):
                amt = t.amount or 0.0
                from_st = t.from_branch_id.name if t.from_branch_id else None
                to_st = t.to_branch_id.name if t.to_branch_id else None
                if from_st and from_st in report_data['opening_balance']:
                    report_data['opening_balance'][from_st] -= amt
                if to_st and to_st in report_data['opening_balance']:
                    report_data['opening_balance'][to_st] += amt

        def process_records(domain, model, is_comparison=False):
            d = list(domain)
            if tenant_id:
                d.append(('tenant_id', '=', tenant_id))
            elif user.havano_role != 'super_admin':
                d.append(('id', '=', 0))

            records = self.env[model].sudo().search(d)

            for rec in records:
                if model == 'havanoposdesk.sale':
                    amt = rec.amount_total or 0.0
                    st_name = rec.store_id.name if rec.store_id else None
                    target_cols = []
                    if st_name:
                        target_cols.append(f"{st_name} (Prev)" if is_comparison else st_name)
                    target_cols.append("Total (Prev)" if is_comparison else "Total")

                    for col in target_cols:
                        if col in report_data['sales']:
                            report_data['sales'][col] += amt

                elif model == 'havanoposdesk.expense':
                    amt = rec.amount or 0.0
                    st_name = rec.store_id.name if rec.store_id else None
                    exp_cat = rec.account_id.name if rec.account_id else (rec.description or 'General Expenses')

                    target_cols = []
                    if st_name:
                        target_cols.append(f"{st_name} (Prev)" if is_comparison else st_name)
                    target_cols.append("Total (Prev)" if is_comparison else "Total")

                    for col in target_cols:
                        if col in report_data['expenses']:
                            report_data['expenses'][col] += amt

                    if exp_cat not in report_data['expense_lines']:
                        report_data['expense_lines'][exp_cat] = {c: 0.0 for c in columns}
                    for col in target_cols:
                        if col in report_data['expense_lines'][exp_cat]:
                            report_data['expense_lines'][exp_cat][col] += amt

                elif model == 'havanoposdesk.payment':
                    if rec.pos_sale_ids or (rec.sale_id and rec.sale_id.state in ['done', 'confirmed']):
                        continue
                    amt = rec.amount or 0.0
                    is_inflow = (rec.payment_type == 'receipt')
                    st_name = rec.store_id.name if rec.store_id else None

                    target_cols = []
                    if st_name:
                        target_cols.append(f"{st_name} (Prev)" if is_comparison else st_name)
                    target_cols.append("Total (Prev)" if is_comparison else "Total")

                    target_dict = report_data['customer_receipts'] if is_inflow else report_data['supplier_payments']
                    for col in target_cols:
                        if col in target_dict:
                            target_dict[col] += amt

                elif model == 'havanoposdesk.cash.transfer':
                    amt = rec.amount or 0.0
                    from_st = rec.from_branch_id.name if rec.from_branch_id else None
                    to_st = rec.to_branch_id.name if rec.to_branch_id else None

                    # Outflow leg
                    out_cols = []
                    if from_st:
                        out_cols.append(f"{from_st} (Prev)" if is_comparison else from_st)
                    for col in out_cols:
                        if col in report_data['transfers_out']:
                            report_data['transfers_out'][col] += amt

                    # Inflow leg
                    in_cols = []
                    if to_st:
                        in_cols.append(f"{to_st} (Prev)" if is_comparison else to_st)
                    for col in in_cols:
                        if col in report_data['transfers_in']:
                            report_data['transfers_in'][col] += amt

        # Process current and comparison periods
        process_records(domain_sale, 'havanoposdesk.sale')
        process_records(domain_expense, 'havanoposdesk.expense')
        process_records(domain_payment, 'havanoposdesk.payment')
        process_records(domain_transfer, 'havanoposdesk.cash.transfer')

        if has_comparison:
            process_records(comp_domain_sale, 'havanoposdesk.sale', is_comparison=True)
            process_records(comp_domain_expense, 'havanoposdesk.expense', is_comparison=True)
            process_records(comp_domain_payment, 'havanoposdesk.payment', is_comparison=True)
            process_records(comp_domain_transfer, 'havanoposdesk.cash.transfer', is_comparison=True)

        def calculate_percent(current, previous):
            if previous == 0:
                return 100.0 if current > 0 else (0.0 if current == 0 else -100.0)
            return ((current - previous) / abs(previous)) * 100.0

        # Calculate totals, net movement, and closing balances
        for col in columns:
            if not col.endswith('(%)'):
                inflows = report_data['sales'].get(col, 0.0) + report_data['customer_receipts'].get(col, 0.0) + report_data['transfers_in'].get(col, 0.0)
                report_data['total_inflows'][col] = inflows

                outflows = report_data['expenses'].get(col, 0.0) + report_data['supplier_payments'].get(col, 0.0) + report_data['transfers_out'].get(col, 0.0)
                report_data['total_outflows'][col] = outflows

                net = inflows - outflows
                report_data['net_movement'][col] = net

                op = report_data['opening_balance'].get(col, 0.0)
                report_data['closing_balance'][col] = op + net

        # Calculate percentages if comparison enabled
        if has_comparison:
            for s in stores:
                cur_col = s['name']
                prev_col = f"{s['name']} (Prev)"
                pct_col = f"{s['name']} (%)"

                for key in ['opening_balance', 'sales', 'customer_receipts', 'transfers_in', 'total_inflows',
                            'expenses', 'transfers_out', 'supplier_payments', 'total_outflows', 'net_movement', 'closing_balance']:
                    report_data[key][pct_col] = calculate_percent(report_data[key].get(cur_col, 0.0), report_data[key].get(prev_col, 0.0))

                for exp_cat, amounts in report_data['expense_lines'].items():
                    amounts[pct_col] = calculate_percent(amounts.get(cur_col, 0.0), amounts.get(prev_col, 0.0))

        # Format rows into arrays corresponding to columns
        final_data = {
            'columns': columns,
            'currency_symbol': report_data['currency_symbol'],
            'opening_balance': [report_data['opening_balance'].get(c, 0.0) for c in columns],
            'sales': [report_data['sales'].get(c, 0.0) for c in columns],
            'customer_receipts': [report_data['customer_receipts'].get(c, 0.0) for c in columns],
            'transfers_in': [report_data['transfers_in'].get(c, 0.0) for c in columns],
            'total_inflows': [report_data['total_inflows'].get(c, 0.0) for c in columns],
            'expenses': [report_data['expenses'].get(c, 0.0) for c in columns],
            'expense_lines': [
                {'name': exp_cat, 'amounts': [amounts.get(c, 0.0) for c in columns]}
                for exp_cat, amounts in report_data['expense_lines'].items()
            ],
            'transfers_out': [report_data['transfers_out'].get(c, 0.0) for c in columns],
            'supplier_payments': [report_data['supplier_payments'].get(c, 0.0) for c in columns],
            'total_outflows': [report_data['total_outflows'].get(c, 0.0) for c in columns],
            'net_movement': [report_data['net_movement'].get(c, 0.0) for c in columns],
            'closing_balance': [report_data['closing_balance'].get(c, 0.0) for c in columns],
        }

        # Accounts for the live balances section (strictly isolated)
        acc_domain = [('tenant_id', '=', tenant_id)] if tenant_id else ([('id', '=', 0)] if user.havano_role != 'super_admin' else [])
        accounts = self.env['havanoposdesk.account'].sudo().search(acc_domain)

        final_data['accounts'] = [{
            'id': a.id,
            'name': a.name,
            'type': a.type or 'Cash',
            'balance': a.balance
        } for a in accounts]

        return final_data

    @api.model
    def generate_xlsx_report(self, date_from=None, date_to=None, store_ids=None, comparison='none'):
        data = self.get_report_data(date_from=date_from, date_to=date_to, store_ids=store_ids, comparison=comparison)
        
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Store Cashbook')
        
        # Formats
        title_fmt = workbook.add_format({'bold': True, 'font_size': 16, 'font_color': '#4c4c4c'})
        subtitle_fmt = workbook.add_format({'font_size': 10, 'font_color': '#666666'})
        header_fmt = workbook.add_format({
            'bold': True, 
            'bg_color': '#714B67', 
            'font_color': '#ffffff', 
            'border': 1, 
            'align': 'center',
            'valign': 'vcenter'
        })
        bold_row_fmt = workbook.add_format({'bold': True, 'bg_color': '#f8f9fa', 'border': 1, 'font_color': '#333333'})
        bold_num_fmt = workbook.add_format({'bold': True, 'bg_color': '#f8f9fa', 'border': 1, 'num_format': '#,##0.00', 'align': 'right', 'font_color': '#333333'})
        norm_row_fmt = workbook.add_format({'border': 1, 'font_color': '#4c4c4c'})
        norm_num_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0.00', 'align': 'right', 'font_color': '#4c4c4c'})
        inflow_title_fmt = workbook.add_format({'bold': True, 'font_color': '#2e7d32', 'border': 1, 'bg_color': '#e8f5e9'})
        inflow_num_fmt = workbook.add_format({'bold': True, 'font_color': '#2e7d32', 'border': 1, 'num_format': '#,##0.00', 'align': 'right', 'bg_color': '#e8f5e9'})
        outflow_title_fmt = workbook.add_format({'bold': True, 'font_color': '#c62828', 'border': 1, 'bg_color': '#ffebee'})
        outflow_num_fmt = workbook.add_format({'bold': True, 'font_color': '#c62828', 'border': 1, 'num_format': '#,##0.00', 'align': 'right', 'bg_color': '#ffebee'})
        closing_title_fmt = workbook.add_format({'bold': True, 'bg_color': '#dcdcdc', 'font_color': '#000000', 'border': 1})
        closing_num_fmt = workbook.add_format({'bold': True, 'bg_color': '#dcdcdc', 'font_color': '#000000', 'border': 1, 'num_format': '#,##0.00', 'align': 'right'})
        
        tenant_id = self._get_active_tenant_id()
        tenant = self.env['havanoposdesk.tenant'].sudo().browse(tenant_id) if tenant_id else False
        tenant_name = tenant.name if tenant else 'Store Cashbook'
        
        # Title
        worksheet.write(0, 0, f"{tenant_name} - Store Cashbook", title_fmt)
        period_str = f"Period: {date_from or 'All Time'} to {date_to or 'Present'}"
        worksheet.write(1, 0, period_str, subtitle_fmt)
        
        cols = data.get('columns', ['Total'])
        worksheet.set_column(0, 0, 36)
        for col_idx in range(len(cols)):
            worksheet.set_column(col_idx + 1, col_idx + 1, 16)
            
        row = 3
        worksheet.write(row, 0, "Line Item", header_fmt)
        for col_idx, col_name in enumerate(cols):
            worksheet.write(row, col_idx + 1, col_name, header_fmt)
            
        # Opening Cash Balance
        row += 1
        worksheet.write(row, 0, "Opening Cash Balance", bold_row_fmt)
        for col_idx, val in enumerate(data.get('opening_balance', [])):
            worksheet.write(row, col_idx + 1, val, bold_num_fmt)
            
        # Inflows Section
        row += 1
        worksheet.write(row, 0, "Cash Inflows (+)", inflow_title_fmt)
        for col_idx in range(len(cols)):
            worksheet.write(row, col_idx + 1, "", inflow_title_fmt)
            
        row += 1
        worksheet.write(row, 0, "  POS Sales (Cash In)", norm_row_fmt)
        for col_idx, val in enumerate(data.get('sales', [])):
            worksheet.write(row, col_idx + 1, val, norm_num_fmt)
            
        row += 1
        worksheet.write(row, 0, "  Customer Debt Receipts", norm_row_fmt)
        for col_idx, val in enumerate(data.get('customer_receipts', [])):
            worksheet.write(row, col_idx + 1, val, norm_num_fmt)
            
        row += 1
        worksheet.write(row, 0, "  Transfers In from Branches", norm_row_fmt)
        for col_idx, val in enumerate(data.get('transfers_in', [])):
            worksheet.write(row, col_idx + 1, val, norm_num_fmt)
            
        row += 1
        worksheet.write(row, 0, "Total Cash Inflows", inflow_title_fmt)
        for col_idx, val in enumerate(data.get('total_inflows', [])):
            worksheet.write(row, col_idx + 1, val, inflow_num_fmt)
            
        # Outflows Section
        row += 1
        worksheet.write(row, 0, "Less Cash Outflows (-)", outflow_title_fmt)
        for col_idx in range(len(cols)):
            worksheet.write(row, col_idx + 1, "", outflow_title_fmt)
            
        row += 1
        worksheet.write(row, 0, "  Store Operating Expenses", norm_row_fmt)
        for col_idx, val in enumerate(data.get('expenses', [])):
            worksheet.write(row, col_idx + 1, val, norm_num_fmt)
            
        for exp_line in data.get('expense_lines', []):
            row += 1
            worksheet.write(row, 0, f"    • {exp_line['name']}", norm_row_fmt)
            for col_idx, val in enumerate(exp_line.get('amounts', [])):
                worksheet.write(row, col_idx + 1, val, norm_num_fmt)
                
        row += 1
        worksheet.write(row, 0, "  Transfers Out / Cashed Up to HQ", norm_row_fmt)
        for col_idx, val in enumerate(data.get('transfers_out', [])):
            worksheet.write(row, col_idx + 1, val, norm_num_fmt)
            
        row += 1
        worksheet.write(row, 0, "  Supplier Payments", norm_row_fmt)
        for col_idx, val in enumerate(data.get('supplier_payments', [])):
            worksheet.write(row, col_idx + 1, val, norm_num_fmt)
            
        row += 1
        worksheet.write(row, 0, "Total Cash Outflows", outflow_title_fmt)
        for col_idx, val in enumerate(data.get('total_outflows', [])):
            worksheet.write(row, col_idx + 1, val, outflow_num_fmt)
            
        # Net Movement
        row += 1
        worksheet.write(row, 0, "Net Cash Movement (Period)", bold_row_fmt)
        for col_idx, val in enumerate(data.get('net_movement', [])):
            worksheet.write(row, col_idx + 1, val, bold_num_fmt)
            
        # Closing Cash Balance
        row += 1
        worksheet.write(row, 0, "Closing Cash Balance", closing_title_fmt)
        for col_idx, val in enumerate(data.get('closing_balance', [])):
            worksheet.write(row, col_idx + 1, val, closing_num_fmt)
            
        # Live Accounts
        if data.get('accounts'):
            row += 2
            worksheet.write(row, 0, "Live Account Balances (Real-time)", header_fmt)
            worksheet.write(row, 1, "Type", header_fmt)
            worksheet.write(row, 2, "Current Balance", header_fmt)
            for acc in data['accounts']:
                row += 1
                worksheet.write(row, 0, acc.get('name', ''), norm_row_fmt)
                worksheet.write(row, 1, acc.get('type', 'Cash'), norm_row_fmt)
                worksheet.write(row, 2, acc.get('balance', 0.0), norm_num_fmt)
                
        workbook.close()
        output.seek(0)
        return output.read()
