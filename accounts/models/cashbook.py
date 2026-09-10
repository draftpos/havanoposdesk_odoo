from odoo import models, fields, api, _
from datetime import datetime
from dateutil.relativedelta import relativedelta

class CashbookReport(models.AbstractModel):
    _name = 'havanoposdesk.cashbook'
    _description = 'Cashbook Report Data'

    @api.model
    def get_available_stores(self):
        domain = []
        if self.env.user.tenant_id:
            domain = [('tenant_id', '=', self.env.user.tenant_id.id)]
        stores = self.env['havanoposdesk.store'].sudo().search_read(domain, ['id', 'name'])
        if not stores:
            stores = self.env['havanoposdesk.store'].sudo().search_read([], ['id', 'name'])
        return stores

    @api.model
    def get_available_accounts(self):
        domain = []
        if self.env.user.tenant_id:
            domain = [('tenant_id', '=', self.env.user.tenant_id.id)]
        accounts = self.env['havanoposdesk.account'].sudo().search_read(domain, ['id', 'name', 'type', 'balance'])
        if not accounts:
            accounts = self.env['havanoposdesk.account'].sudo().search_read([], ['id', 'name', 'type', 'balance'])
        return accounts

    @api.model
    def get_report_data(self, date_from=None, date_to=None, store_ids=None, comparison='none'):
        user_tenant = self.env.user.tenant_id
        tenant_id = user_tenant.id if user_tenant else False

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

        # Stores to process
        stores = []
        if store_ids:
            store_records = self.env['havanoposdesk.store'].sudo().browse(store_ids)
            for st in store_records:
                if st.exists():
                    stores.append({'id': st.id, 'name': st.name})
        else:
            all_st = self.env['havanoposdesk.store'].sudo().search([])
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
            if tenant_id:
                domain = domain + [('tenant_id', '=', tenant_id)]
            records = self.env[model].sudo().search(domain)
            if not records and tenant_id:
                records = self.env[model].sudo().search(domain[:-1])

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

        # Accounts for the live balances section
        acc_domain = []
        if tenant_id:
            acc_domain.append(('tenant_id', '=', tenant_id))
        accounts = self.env['havanoposdesk.account'].sudo().search(acc_domain)
        if not accounts:
            accounts = self.env['havanoposdesk.account'].sudo().search([])

        final_data['accounts'] = [{
            'id': a.id,
            'name': a.name,
            'type': a.type or 'Cash',
            'balance': a.balance
        } for a in accounts]

        return final_data
