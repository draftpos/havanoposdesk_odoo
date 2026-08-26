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
    
    total_expenses = fields.Monetary(string='Total Expenses', currency_field='currency_id', default=0.0)
    total_credit_notes = fields.Monetary(string='Total Credit Notes', currency_field='currency_id', default=0.0)

    # Payment Breakdown
    amount_cash = fields.Monetary(string='Total Cash Payments', currency_field='currency_id', default=0.0)
    amount_card = fields.Monetary(string='Total Card Payments', currency_field='currency_id', default=0.0)
    amount_mobile = fields.Monetary(string='Total Mobile Payments', currency_field='currency_id', default=0.0)
    amount_bank = fields.Monetary(string='Total Bank Transfers', currency_field='currency_id', default=0.0)
    amount_other = fields.Monetary(string='Total Other Payments', currency_field='currency_id', default=0.0)

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
