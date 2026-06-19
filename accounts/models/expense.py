from odoo import models, fields, api

class Expense(models.Model):
    _name = 'havanoposdesk.expense'
    _description = 'Expense Posting'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    account_id = fields.Many2one('havanoposdesk.account', string='Expense Account', domain=[('type', '=', 'Expense')], required=True)
    amount = fields.Float(string='Amount', required=True)
    description = fields.Text(string='Description')
    state = fields.Selection([
        ('Draft', 'Draft'),
        ('Posted', 'Posted')
    ], string='Status', readonly=True, default='Draft')
    
    # Store reference
    store_id = fields.Many2one('havanoposdesk.store', string='Store')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                # Generate sequence if we have one, otherwise fallback to New
                vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.expense') or 'New'
        return super().create(vals_list)

    def action_post(self):
        for record in self:
            if record.state == 'Draft':
                record.state = 'Posted'
