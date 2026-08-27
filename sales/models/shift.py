from odoo import models, fields, api

class Shift(models.Model):
    _name = 'havanoposdesk.shift'
    _description = 'Shift Operations'
    _order = 'start_date desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', default=lambda self: self.env.user.tenant_id.id, index=True, readonly=True)
    user_id = fields.Many2one('res.users', string='Cashier', default=lambda self: self.env.user.id, required=True)
    store_id = fields.Many2one('havanoposdesk.store', string='Store', required=True)
    terminal_id = fields.Many2one('havanoposdesk.pos.terminal', string='Terminal')
    
    start_date = fields.Datetime(string='Opened At', default=fields.Datetime.now, required=True)
    end_date = fields.Datetime(string='Closed At')
    
    state = fields.Selection([
        ('open', 'Open'),
        ('closed', 'Closed')
    ], string='Status', default='open', required=True, tracking=True)

    currency_id = fields.Many2one('res.currency', string='Currency', related='tenant_id.currency_id', readonly=True)

    opening_cash = fields.Monetary(string='Opening Cash (Before)', currency_field='currency_id', default=0.0)
    actual_cash = fields.Monetary(string='Actual Cash (After)', currency_field='currency_id', default=0.0)
    expected_cash = fields.Monetary(string='Expected Cash', currency_field='currency_id', compute='_compute_expected_cash', store=True)
    cash_difference = fields.Monetary(string='Difference', currency_field='currency_id', compute='_compute_cash_difference', store=True)
    
    total_expenses = fields.Monetary(string='Total Expenses', currency_field='currency_id', compute='_compute_total_expenses', store=True, readonly=False, default=0.0)
    total_credit_notes = fields.Monetary(string='Total Credit Notes', currency_field='currency_id', default=0.0)

    # Payment Breakdown
    amount_cash = fields.Monetary(string='Total Cash Payments', currency_field='currency_id', default=0.0)
    amount_card = fields.Monetary(string='Total Card Payments', currency_field='currency_id', default=0.0)
    amount_mobile = fields.Monetary(string='Total Mobile Payments', currency_field='currency_id', default=0.0)
    amount_bank = fields.Monetary(string='Total Bank Transfers', currency_field='currency_id', default=0.0)
    amount_other = fields.Monetary(string='Total Other Payments', currency_field='currency_id', default=0.0)

    sale_ids = fields.One2many('havanoposdesk.sale', 'shift_id', string='Sales')
    expense_ids = fields.One2many('havanoposdesk.expense', 'shift_id', string='Expenses')
    cash_transfer_ids = fields.One2many('havanoposdesk.cash.transfer', 'shift_id', string='Cash Transfers / Cash Up')
    cash_transferred_amount = fields.Monetary(string='Total Cashed Up / Transferred', compute='_compute_cash_transferred', currency_field='currency_id')
    cash_transfer_count = fields.Integer(string='Cash Transfers Count', compute='_compute_cash_transferred')

    @api.depends('expense_ids.amount', 'expense_ids.state', 'expense_ids.is_paid')
    def _compute_total_expenses(self):
        for shift in self:
            paid_posted_expenses = shift.expense_ids.filtered(lambda e: e.state == 'Posted' and e.is_paid)
            if paid_posted_expenses:
                shift.total_expenses = sum(paid_posted_expenses.mapped('amount'))
            elif not shift.total_expenses:
                shift.total_expenses = 0.0

    @api.depends('cash_transfer_ids.amount', 'cash_transfer_ids.state')
    def _compute_cash_transferred(self):
        for shift in self:
            posted_transfers = shift.cash_transfer_ids.filtered(lambda t: t.state == 'posted')
            shift.cash_transferred_amount = sum(posted_transfers.mapped('amount'))
            shift.cash_transfer_count = len(shift.cash_transfer_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.shift') or 'New'
        return super(Shift, self).create(vals_list)

    @api.depends('opening_cash', 'amount_cash', 'total_expenses', 'total_credit_notes')
    def _compute_expected_cash(self):
        for record in self:
            record.expected_cash = (record.opening_cash + record.amount_cash) - record.total_expenses

    @api.depends('actual_cash', 'expected_cash')
    def _compute_cash_difference(self):
        for record in self:
            record.cash_difference = record.actual_cash - record.expected_cash

    def action_close_shift(self):
        for record in self:
            record.write({
                'state': 'closed',
                'end_date': fields.Datetime.now()
            })

    def action_cash_up(self):
        """Open Cash Transfer form pre-filled to transfer closing cash from branch to HQ/Main store."""
        self.ensure_one()
        # Find default store / HQ store for this tenant
        hq_store = self.env['havanoposdesk.store'].search([
            ('tenant_id', '=', self.tenant_id.id),
            ('is_default', '=', True),
        ], limit=1)
        if not hq_store or hq_store.id == self.store_id.id:
            hq_store = self.env['havanoposdesk.store'].search([
                ('tenant_id', '=', self.tenant_id.id),
                ('id', '!=', self.store_id.id),
            ], limit=1)

        amount_to_transfer = self.actual_cash if self.actual_cash > 0 else self.expected_cash
        if amount_to_transfer <= 0:
            amount_to_transfer = self.amount_cash

        # Auto-find source and target cash accounts
        from_acc = self.env['havanoposdesk.account'].search([
            ('tenant_id', '=', self.tenant_id.id),
            ('type', '=', 'Cash'),
            ('active', '=', True),
            '|', ('store_id', '=', self.store_id.id), ('store_ids', 'in', self.store_id.id)
        ], limit=1)
        
        to_acc = False
        if hq_store:
            to_acc = self.env['havanoposdesk.account'].search([
                ('tenant_id', '=', self.tenant_id.id),
                ('type', '=', 'Cash'),
                ('active', '=', True),
                '|', ('store_id', '=', hq_store.id), ('store_ids', 'in', hq_store.id)
            ], limit=1)

        return {
            'name': 'Shift Cash Up to HQ',
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.cash.transfer',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': {
                'default_store_id': self.store_id.id,
                'default_from_branch_id': self.store_id.id,
                'default_to_branch_id': hq_store.id if hq_store else False,
                'default_from_account_id': from_acc.id if from_acc else False,
                'default_to_account_id': to_acc.id if to_acc else False,
                'default_amount': amount_to_transfer if amount_to_transfer > 0 else 0.0,
                'default_shift_id': self.id,
                'default_tenant_id': self.tenant_id.id,
                'default_reason': f"Shift Cash Up - {self.name} ({self.user_id.name})",
            },
        }

    def action_view_cash_transfers(self):
        self.ensure_one()
        return {
            'name': f"Cash Transfers - Shift {self.name}",
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.cash.transfer',
            'view_mode': 'list,form',
            'domain': [('shift_id', '=', self.id)],
            'context': {
                'default_shift_id': self.id,
                'default_store_id': self.store_id.id,
                'default_from_branch_id': self.store_id.id,
                'default_tenant_id': self.tenant_id.id,
            },
        }
