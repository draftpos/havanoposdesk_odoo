from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

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
    currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_currency_id', store=True, readonly=False)
    tenant_currency_id = fields.Many2one('res.currency', related='tenant_id.currency_id')
    amount_base = fields.Float(string='Base Amount', compute='_compute_amount_base', store=True)
    
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
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if tenant_id:
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
                if tenant and not tenant.check_subscription_active():
                    raise ValidationError(_("Your subscription has expired and the grace period has ended. Please upgrade your package to resume operations."))
            
            if vals.get('name', 'New') == 'New':
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

    def write(self, vals):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'draft' and not self.env.context.get('bypass_payment_check') and any(f not in ['state'] for f in vals.keys()):
                raise ValidationError("You cannot modify a confirmed/posted payment. Please cancel it first.")
        return super().write(vals)

    def unlink(self):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'draft':
                raise ValidationError("You cannot delete a confirmed/posted payment. Please cancel it first.")
        return super().unlink()

    @api.depends('tenant_id')
    def _compute_currency_id(self):
        for record in self:
            if not record.currency_id:
                record.currency_id = record.tenant_id.currency_id

    @api.depends('amount', 'currency_id', 'tenant_currency_id', 'date')
    def _compute_amount_base(self):
        for record in self:
            if not record.currency_id or not record.tenant_currency_id or record.currency_id == record.tenant_currency_id:
                record.amount_base = record.amount
            else:
                date = record.date or fields.Date.context_today(self)
                record.amount_base = record.currency_id._convert(
                    record.amount, record.tenant_currency_id, self.env.company, date
                )

    def action_post(self):
        for payment in self:
            if payment.state != 'draft':
                raise UserError("Only draft payments can be posted.")
            if payment.amount <= 0:
                raise UserError("Payment amount must be greater than zero.")
                
            # Update Account Balance using sudo()
            if payment.payment_type == 'receipt':
                payment.account_id.sudo().balance += payment.amount_base
            else:
                payment.account_id.sudo().balance -= payment.amount_base
                
            payment.write({'state': 'posted'})

    def action_cancel(self):
        for payment in self:
            if payment.state != 'posted':
                payment.write({'state': 'cancelled'})
                continue
                
            # Reverse Account Balance using sudo()
            if payment.payment_type == 'receipt':
                payment.account_id.sudo().balance -= payment.amount_base
            else:
                payment.account_id.sudo().balance += payment.amount_base
                
            payment.write({'state': 'cancelled'})

    def action_draft(self):
        for payment in self:
            if payment.state == 'cancelled':
                payment.write({'state': 'draft'})
