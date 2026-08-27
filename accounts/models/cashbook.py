from odoo import models, fields, api, _
from datetime import datetime, time

class CashbookReport(models.AbstractModel):
    _name = 'havanoposdesk.cashbook'
    _description = 'Cashbook Report & Movement Tracking'

    @api.model
    def get_available_stores(self):
        domain = []
        if self.env.user.tenant_id:
            domain = [('tenant_id', '=', self.env.user.tenant_id.id)]
        return self.env['havanoposdesk.store'].sudo().search_read(domain, ['id', 'name', 'code'])

    @api.model
    def get_available_accounts(self, store_ids=None):
        domain = [('type', 'in', ['Cash', 'Bank']), ('active', '=', True)]
        if self.env.user.tenant_id:
            domain.append(('tenant_id', '=', self.env.user.tenant_id.id))
        if store_ids:
            domain.append('|')
            domain.append(('store_id', 'in', store_ids))
            domain.append(('store_ids', 'in', store_ids))
        return self.env['havanoposdesk.account'].sudo().search_read(domain, ['id', 'name', 'type', 'balance', 'currency_id'])

    @api.model
    def get_report_data(self, store_ids=None, account_ids=None, date_from=None, date_to=None):
        tenant_id = self.env.user.tenant_id.id if self.env.user.tenant_id else False

        # Filter stores
        store_domain = []
        if tenant_id:
            store_domain.append(('tenant_id', '=', tenant_id))
        if store_ids:
            store_domain.append(('id', 'in', store_ids))
        stores = self.env['havanoposdesk.store'].sudo().search(store_domain)
        valid_store_ids = stores.ids if store_ids else []

        # Filter accounts
        acc_domain = [('type', 'in', ['Cash', 'Bank']), ('active', '=', True)]
        if tenant_id:
            acc_domain.append(('tenant_id', '=', tenant_id))
        if account_ids:
            acc_domain.append(('id', 'in', account_ids))
        accounts = self.env['havanoposdesk.account'].sudo().search(acc_domain)
        valid_account_ids = accounts.ids if account_ids else []

        # Parse date range
        dt_from = None
        dt_to = None
        if date_from:
            try:
                dt_from = datetime.strptime(f"{date_from} 00:00:00", "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    dt_from = datetime.strptime(date_from[:10], "%Y-%m-%d")
                except Exception:
                    pass
        if date_to:
            try:
                dt_to = datetime.strptime(f"{date_to} 23:59:59", "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    dt_to = datetime.strptime(f"{date_to[:10]} 23:59:59", "%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

        all_raw_movements = []

        # 1. POS & Invoiced Sales
        sale_domain = [('state', 'in', ['done', 'confirmed'])]
        if tenant_id:
            sale_domain.append(('tenant_id', '=', tenant_id))
        if valid_store_ids:
            sale_domain.append(('store_id', 'in', valid_store_ids))

        sales = self.env['havanoposdesk.sale'].sudo().search(sale_domain)
        for s in sales:
            acc = s.account_id
            if valid_account_ids and acc and acc.id not in valid_account_ids:
                continue

            sale_dt = None
            if s.date:
                sale_dt = s.date if isinstance(s.date, datetime) else datetime.combine(s.date, time.min)
            elif s.posting_date:
                sale_dt = datetime.combine(s.posting_date, time.min)
            elif s.create_date:
                sale_dt = s.create_date
            else:
                sale_dt = fields.Datetime.now()

            amount = s.amount_total or 0.0
            if amount > 0:
                all_raw_movements.append({
                    'timestamp': sale_dt,
                    'date_str': sale_dt.strftime('%Y-%m-%d %H:%M'),
                    'type': 'sale',
                    'type_label': 'POS Sale',
                    'category': 'inflow',
                    'reference': s.name or 'Sale',
                    'party': s.customer.name if s.customer else 'Walk-in Customer',
                    'store_id': s.store_id.id if s.store_id else False,
                    'store_name': s.store_id.name if s.store_id else 'Store',
                    'account_id': acc.id if acc else False,
                    'account_name': acc.name if acc else 'Cash Account',
                    'amount_in': amount,
                    'amount_out': 0.0,
                    'user_name': s.cashier_id.name if s.cashier_id else (s.create_uid.name if s.create_uid else 'Cashier'),
                    'note': f"Sale {s.name}"
                })

        # 2. Payments (Direct Customer Receipts, Supplier Payments, Payment Entries)
        pay_domain = [('state', 'in', ['posted', 'Posted'])]
        if tenant_id:
            pay_domain.append(('tenant_id', '=', tenant_id))
        if valid_store_ids:
            pay_domain.append('|')
            pay_domain.append(('store_id', 'in', valid_store_ids))
            pay_domain.append(('store_id', '=', False))

        payments = self.env['havanoposdesk.payment'].sudo().search(pay_domain)
        for p in payments:
            if p.pos_sale_ids or (p.sale_id and p.sale_id.state in ['done', 'confirmed']):
                continue
            acc = p.account_id
            if valid_account_ids and acc and acc.id not in valid_account_ids:
                continue

            pay_dt = None
            if p.date:
                pay_dt = datetime.combine(p.date, time.min)
            elif p.create_date:
                pay_dt = p.create_date
            else:
                pay_dt = fields.Datetime.now()

            amount = p.amount or 0.0
            is_inflow = (p.payment_type == 'receipt')
            all_raw_movements.append({
                'timestamp': pay_dt,
                'date_str': pay_dt.strftime('%Y-%m-%d %H:%M'),
                'type': 'customer_receipt' if is_inflow else 'supplier_payment',
                'type_label': 'Customer Receipt' if is_inflow else 'Supplier Payment',
                'category': 'inflow' if is_inflow else 'outflow',
                'reference': p.name or 'Payment',
                'party': (p.customer_id.name if p.customer_id else (p.supplier_id.name if p.supplier_id else (p.reference or 'Direct Payment'))),
                'store_id': p.store_id.id if p.store_id else False,
                'store_name': p.store_id.name if p.store_id else 'HQ Store',
                'account_id': acc.id if acc else False,
                'account_name': acc.name if acc else 'Cash/Bank',
                'amount_in': amount if is_inflow else 0.0,
                'amount_out': amount if not is_inflow else 0.0,
                'user_name': p.create_uid.name if p.create_uid else 'User',
                'note': p.reference or ''
            })

        # 3. Expenses (Paid Cash/Bank Outflows)
        exp_domain = [('state', 'in', ['Posted', 'posted']), ('is_paid', '=', True)]
        if tenant_id:
            exp_domain.append(('tenant_id', '=', tenant_id))
        if valid_store_ids:
            exp_domain.append(('store_id', 'in', valid_store_ids))

        expenses = self.env['havanoposdesk.expense'].sudo().search(exp_domain)
        for e in expenses:
            pay_acc = e.payment_account_id
            if valid_account_ids and pay_acc and pay_acc.id not in valid_account_ids:
                continue

            exp_dt = None
            if e.date:
                exp_dt = datetime.combine(e.date, time.min)
            elif e.create_date:
                exp_dt = e.create_date
            else:
                exp_dt = fields.Datetime.now()

            amount = e.amount or 0.0
            if amount > 0:
                all_raw_movements.append({
                    'timestamp': exp_dt,
                    'date_str': exp_dt.strftime('%Y-%m-%d %H:%M'),
                    'type': 'expense',
                    'type_label': 'Expense Payout',
                    'category': 'outflow',
                    'reference': e.name or 'Expense',
                    'party': e.account_id.name if e.account_id else (e.description or 'General Expense'),
                    'store_id': e.store_id.id if e.store_id else False,
                    'store_name': e.store_id.name if e.store_id else 'Store',
                    'account_id': pay_acc.id if pay_acc else False,
                    'account_name': pay_acc.name if pay_acc else 'Cash Account',
                    'amount_in': 0.0,
                    'amount_out': amount,
                    'user_name': e.create_uid.name if e.create_uid else 'Cashier',
                    'note': e.description or e.account_id.name or ''
                })

        # 4. Cash Transfers (Outflows from source, Inflows to destination)
        transfer_domain = [('state', 'in', ['posted', 'Posted'])]
        if tenant_id:
            transfer_domain.append(('tenant_id', '=', tenant_id))

        transfers = self.env['havanoposdesk.cash.transfer'].sudo().search(transfer_domain)
        for t in transfers:
            trans_dt = None
            if t.date:
                trans_dt = datetime.combine(t.date, time.min)
            elif t.create_date:
                trans_dt = t.create_date
            else:
                trans_dt = fields.Datetime.now()

            amount = t.amount or 0.0
            if amount <= 0:
                continue

            # Outflow leg (From Branch / From Account)
            include_outflow = True
            if valid_store_ids and t.from_branch_id and t.from_branch_id.id not in valid_store_ids:
                include_outflow = False
            if valid_account_ids and t.from_account_id and t.from_account_id.id not in valid_account_ids:
                include_outflow = False

            if include_outflow:
                all_raw_movements.append({
                    'timestamp': trans_dt,
                    'date_str': trans_dt.strftime('%Y-%m-%d %H:%M'),
                    'type': 'transfer_out',
                    'type_label': 'Transfer Out / Cash Up',
                    'category': 'outflow',
                    'reference': t.name or 'Transfer',
                    'party': f"To: {t.to_branch_id.name if t.to_branch_id else (t.to_account_id.name if t.to_account_id else 'Safe')}",
                    'store_id': t.from_branch_id.id if t.from_branch_id else False,
                    'store_name': t.from_branch_id.name if t.from_branch_id else 'Store',
                    'account_id': t.from_account_id.id if t.from_account_id else False,
                    'account_name': t.from_account_id.name if t.from_account_id else 'Cash Account',
                    'amount_in': 0.0,
                    'amount_out': amount,
                    'user_name': t.create_uid.name if t.create_uid else 'User',
                    'note': t.reason or 'Cash Transfer Out'
                })

            # Inflow leg (To Branch / To Account)
            include_inflow = True
            if valid_store_ids and t.to_branch_id and t.to_branch_id.id not in valid_store_ids:
                include_inflow = False
            if valid_account_ids and t.to_account_id and t.to_account_id.id not in valid_account_ids:
                include_inflow = False

            if include_inflow:
                all_raw_movements.append({
                    'timestamp': trans_dt,
                    'date_str': trans_dt.strftime('%Y-%m-%d %H:%M'),
                    'type': 'transfer_in',
                    'type_label': 'Transfer In',
                    'category': 'inflow',
                    'reference': t.name or 'Transfer',
                    'party': f"From: {t.from_branch_id.name if t.from_branch_id else (t.from_account_id.name if t.from_account_id else 'Branch')}",
                    'store_id': t.to_branch_id.id if t.to_branch_id else False,
                    'store_name': t.to_branch_id.name if t.to_branch_id else 'Store',
                    'account_id': t.to_account_id.id if t.to_account_id else False,
                    'account_name': t.to_account_id.name if t.to_account_id else 'Cash Account',
                    'amount_in': amount,
                    'amount_out': 0.0,
                    'user_name': t.create_uid.name if t.create_uid else 'User',
                    'note': t.reason or 'Cash Transfer In'
                })

        # Sort all movements chronologically
        all_raw_movements.sort(key=lambda m: m['timestamp'])

        # Split into Opening Balance (before dt_from) and Period Movements
        opening_balance = 0.0
        period_sales = 0.0
        period_customer_receipts = 0.0
        period_transfers_in = 0.0
        period_expenses = 0.0
        period_supplier_payments = 0.0
        period_transfers_out = 0.0

        period_movements = []
        running_bal = 0.0

        for m in all_raw_movements:
            ts = m['timestamp']
            net_change = m['amount_in'] - m['amount_out']

            if dt_from and ts < dt_from:
                opening_balance += net_change
            elif (not dt_to) or (ts <= dt_to):
                if m['type'] == 'sale':
                    period_sales += m['amount_in']
                elif m['type'] == 'customer_receipt':
                    period_customer_receipts += m['amount_in']
                elif m['type'] == 'transfer_in':
                    period_transfers_in += m['amount_in']
                elif m['type'] == 'expense':
                    period_expenses += m['amount_out']
                elif m['type'] == 'supplier_payment':
                    period_supplier_payments += m['amount_out']
                elif m['type'] == 'transfer_out':
                    period_transfers_out += m['amount_out']

                if not period_movements:
                    running_bal = opening_balance + net_change
                else:
                    running_bal += net_change

                movement_copy = dict(m)
                del movement_copy['timestamp']
                movement_copy['running_balance'] = round(running_bal, 2)
                period_movements.append(movement_copy)

        display_movements = list(reversed(period_movements))

        total_inflows = period_sales + period_customer_receipts + period_transfers_in
        total_outflows = period_expenses + period_supplier_payments + period_transfers_out
        closing_balance = opening_balance + total_inflows - total_outflows

        # Live Real-time Account Balances
        all_accounts = self.env['havanoposdesk.account'].sudo().search(acc_domain)
        live_account_balances = []
        for acc in all_accounts:
            live_account_balances.append({
                'id': acc.id,
                'name': acc.name,
                'type': acc.type,
                'balance': acc.balance,
                'currency': acc.currency_id.name if acc.currency_id else 'USD'
            })

        currency_symbol = self.env.user.tenant_id.currency_id.symbol or '$' if self.env.user.tenant_id and self.env.user.tenant_id.currency_id else '$'

        return {
            'currency_symbol': currency_symbol,
            'date_from': date_from or '',
            'date_to': date_to or '',
            'opening_balance': round(opening_balance, 2),
            'total_inflows': round(total_inflows, 2),
            'total_outflows': round(total_outflows, 2),
            'closing_balance': round(closing_balance, 2),
            'net_movement': round(total_inflows - total_outflows, 2),
            'breakdown': {
                'sales': round(period_sales, 2),
                'customer_receipts': round(period_customer_receipts, 2),
                'transfers_in': round(period_transfers_in, 2),
                'expenses': round(period_expenses, 2),
                'supplier_payments': round(period_supplier_payments, 2),
                'transfers_out': round(period_transfers_out, 2)
            },
            'accounts': live_account_balances,
            'movements': display_movements,
            'total_transactions': len(display_movements)
        }
