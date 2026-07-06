from odoo import models, fields, api

class Expense(models.Model):
    _name = 'havanoposdesk.expense'
    _description = 'Expense Posting'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    account_id = fields.Many2one('havanoposdesk.account', string='Expense Account', domain=[('type', '=', 'Expense')], required=True)
    amount = fields.Float(string='Amount', required=True)
    description = fields.Text(string='Description')
    supplier_id = fields.Many2one('havanoposdesk.supplier', string='Supplier')
    is_paid = fields.Boolean(string='Paid')
    payment_account_id = fields.Many2one(
        'havanoposdesk.account', 
        string='Payment Account', 
        domain="[('type', 'in', ['Cash', 'Bank'])]"
    )
    state = fields.Selection([
        ('Draft', 'Draft'),
        ('Posted', 'Posted'),
        ('Cancelled', 'Cancelled')
    ], string='Status', readonly=True, default='Draft')
    
    # Store reference
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    store_id = fields.Many2one('havanoposdesk.store', string='Store')
    currency_id = fields.Many2one('res.currency', related='store_id.currency_id', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
                if tenant:
                    vals['name'] = tenant._get_next_sequence('exp')
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.expense') or 'New'
        return super().create(vals_list)

    def write(self, vals):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'Draft' and any(f not in ['state'] for f in vals.keys()):
                raise ValidationError("You cannot modify a confirmed/posted expense. Please cancel it first.")
        return super().write(vals)

    def unlink(self):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'Draft':
                raise ValidationError("You cannot delete a confirmed/posted expense. Please cancel it first.")
        return super().unlink()

    def action_post(self):
        for record in self:
            if record.state == 'Draft':
                if record.is_paid:
                    if not record.payment_account_id:
                        from odoo.exceptions import ValidationError
                        raise ValidationError("Please select a Payment Account for paid expenses.")
                    # Subtract from payment account (cash/bank) using sudo()
                    record.payment_account_id.sudo().balance -= record.amount
                    # Add to expense account using sudo()
                    record.account_id.sudo().balance += record.amount
                else:
                    # Just add to expense account if not paid using sudo()
                    record.account_id.sudo().balance += record.amount
                record.state = 'Posted'

    def action_cancel(self):
        for record in self:
            if record.state != 'Posted':
                continue
            if record.is_paid and record.payment_account_id:
                # Reverse subtraction using sudo()
                record.payment_account_id.sudo().balance += record.amount
                # Reverse addition using sudo()
                record.account_id.sudo().balance -= record.amount
            else:
                # Reverse addition using sudo()
                record.account_id.sudo().balance -= record.amount
            record.state = 'Cancelled'

    def action_draft(self):
        for record in self:
            if record.state != 'Cancelled':
                continue
            record.state = 'Draft'
