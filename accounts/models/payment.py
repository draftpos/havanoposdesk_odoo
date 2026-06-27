from odoo import models, fields, api
from odoo.exceptions import UserError

class Payment(models.Model):
    _name = 'havanoposdesk.payment'
    _description = 'Payment'
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    
    payment_type = fields.Selection([
        ('receipt', 'Receive Money'),
        ('payment', 'Send Money')
    ], string='Payment Type', required=True, default='receipt')
    
    partner_type = fields.Selection([
        ('customer', 'Customer'),
        ('supplier', 'Supplier')
    ], string='Partner Type', required=True, default='customer')
    
    customer_id = fields.Many2one('havanoposdesk.customer', string='Customer')
    supplier_id = fields.Many2one('havanoposdesk.supplier', string='Supplier')
    
    account_id = fields.Many2one('havanoposdesk.account', string='Bank/Cash Account', required=True, domain="[('type', 'in', ['Bank', 'Cash'])]")
    
    amount = fields.Float(string='Amount', required=True, default=0.0)
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    reference = fields.Char(string='Memo / Reference')
    pos_sale_ids = fields.One2many('havanoposdesk.sale', 'pos_payment_id', string='POS Sales Breakdown')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled')
    ], string='Status', required=True, default='draft')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
                if tenant:
                    if vals.get('payment_type') == 'payment':
                        vals['name'] = tenant._get_next_sequence('pay_out')
                    else:
                        vals['name'] = tenant._get_next_sequence('pay_in')
                else:
                    if vals.get('payment_type') == 'payment':
                        vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.payment.out') or 'PAY/New'
                    else:
                        vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.payment.in') or 'REC/New'
        return super().create(vals_list)

    def action_post(self):
        for payment in self:
            if payment.state != 'draft':
                raise UserError("Only draft payments can be posted.")
            if payment.amount <= 0:
                raise UserError("Payment amount must be greater than zero.")
                
            # Update Account Balance
            if payment.payment_type == 'receipt':
                payment.account_id.balance += payment.amount
            else:
                payment.account_id.balance -= payment.amount
                
            payment.write({'state': 'posted'})

    def action_cancel(self):
        for payment in self:
            if payment.state != 'posted':
                payment.write({'state': 'cancelled'})
                continue
                
            # Reverse Account Balance
            if payment.payment_type == 'receipt':
                payment.account_id.balance -= payment.amount
            else:
                payment.account_id.balance += payment.amount
                
            payment.write({'state': 'cancelled'})

    def action_draft(self):
        for payment in self:
            if payment.state == 'cancelled':
                payment.write({'state': 'draft'})
