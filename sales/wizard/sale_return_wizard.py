from odoo import models, fields, api
from odoo.exceptions import ValidationError

class SaleReturnWizard(models.TransientModel):
    _name = 'havanoposdesk.sale.return.wizard'
    _description = 'Sale Return Wizard'

    sale_id = fields.Many2one('havanoposdesk.sale', string='Sale', required=True, ondelete='cascade')
    line_ids = fields.One2many('havanoposdesk.sale.return.wizard.line', 'wizard_id', string='Items to Return')
    amount_total = fields.Float(string='Total Refund', compute='_compute_amount_total')
    payment_status_display = fields.Selection([
        ('cash', 'Paid'),
        ('account', 'On Account')
    ], string='Payment Status', default='cash', required=True)
    payment_policy = fields.Selection([
        ('single', 'Single Payment'),
        ('multi', 'Split / Multi-Currency Payment')
    ], string='Payment Policy', default='single')
    account_id = fields.Many2one('havanoposdesk.account', string='Deposit Account', domain="[('type', 'in', ['Cash', 'Bank'])]")
    single_payment_amount = fields.Float(string='Payment Amount')

    @api.onchange('amount_total')
    def _onchange_amount_total(self):
        if self.payment_policy == 'single':
            self.single_payment_amount = self.amount_total

    @api.depends('line_ids.amount')
    def _compute_amount_total(self):
        for record in self:
            record.amount_total = sum(record.line_ids.mapped('amount'))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_id') and self.env.context.get('active_model') == 'havanoposdesk.sale':
            sale = self.env['havanoposdesk.sale'].browse(self.env.context.get('active_id'))
            res['sale_id'] = sale.id
            
            # Default payment status display based on original sale
            if sale.payment_status == 'account':
                res['payment_status_display'] = 'account'
            else:
                res['payment_status_display'] = 'cash'
                if sale.account_id:
                    res['account_id'] = sale.account_id.id
                elif sale.payment_ids:
                    posted_p = sale.payment_ids.filtered(lambda p: p.account_id and p.state != 'cancelled')[:1]
                    if posted_p:
                        res['account_id'] = posted_p.account_id.id

            # Calculate already returned quantities per product
            returned_qtys = {}
            for ret in sale.return_sale_ids:
                if ret.state != 'cancel':
                    for rl in ret.line_ids:
                        key = (rl.product_id.id, rl.variant_id.id if rl.variant_id else False)
                        returned_qtys[key] = returned_qtys.get(key, 0.0) + rl.accepted_qty

            lines = []
            for line in sale.line_ids:
                key = (line.product_id.id, line.variant_id.id if line.variant_id else False)
                remaining_qty = line.accepted_qty - returned_qtys.get(key, 0.0)
                if remaining_qty > 0:
                    lines.append((0, 0, {
                        'sale_line_id': line.id,
                        'product_id': line.product_id.id,
                        'variant_id': line.variant_id.id if line.variant_id else False,
                        'qty_sold': remaining_qty,
                        'qty_returned': 0.0,
                        'rate': line.rate,
                        'tax_ids': [(6, 0, line.tax_ids.ids)],
                    }))
            res['line_ids'] = lines
        return res

    def action_confirm_return(self):
        self.ensure_one()
        
        # Filter lines where return qty > 0
        return_lines = self.line_ids.filtered(lambda l: l.qty_returned > 0)
        
        if not return_lines:
            raise ValidationError("You must specify a return quantity greater than 0 for at least one item.")
            
        # Check if they are doing a second partial return
        has_existing_returns = any(r.state != 'cancel' for r in self.sale_id.return_sale_ids)
        if has_existing_returns:
            total_remaining = sum(l.qty_sold for l in self.line_ids)
            total_returning = sum(l.qty_returned for l in self.line_ids)
            if total_returning < total_remaining:
                raise ValidationError("You cannot perform multiple partial returns. Please return all remaining items in a single credit note, or create a standalone Credit Note.")
            
        store_name = self.sale_id.store or (self.sale_id.store_id.name if self.sale_id.store_id else False)
        
        acc_id = self.account_id.id if (self.payment_status_display == 'cash' and self.account_id) else False
        if not acc_id and self.payment_status_display == 'cash':
            if self.sale_id.account_id:
                acc_id = self.sale_id.account_id.id
            else:
                def_acc = self.env['havanoposdesk.account'].search([
                    ('tenant_id', '=', self.sale_id.tenant_id.id),
                    ('type', 'in', ['Cash', 'Bank']),
                    ('active', '=', True),
                    ('is_on_account', '=', False)
                ], limit=1)
                if def_acc:
                    acc_id = def_acc.id

        sale_vals = {
            'is_return': True,
            'return_id': self.sale_id.id,
            'customer': self.sale_id.customer.id,
            'store_id': self.sale_id.store_id.id if self.sale_id.store_id else False,
            'store': store_name,
            'tenant_id': self.sale_id.tenant_id.id,
            'salesperson_id': self.env.user.id,
            'currency_id': self.sale_id.currency_id.id if self.sale_id.currency_id else False,
            'exchange_rate': self.sale_id.exchange_rate,
            'pricelist_id': self.sale_id.pricelist_id.id if self.sale_id.pricelist_id else False,
            'payment_status': 'cash' if self.payment_status_display == 'cash' else 'account',
            'payment_policy': self.payment_policy,
            'account_id': acc_id,
            'single_payment_amount': self.single_payment_amount,
            'line_ids': [],
        }

        for rline in return_lines:
            if rline.qty_returned > rline.qty_sold:
                raise ValidationError(f"You cannot return more than what was sold for {rline.product_id.name}.")
                
            orig_line = rline.sale_line_id
            variant = rline.variant_id or (orig_line.variant_id if orig_line else False)
            cost = orig_line.cost_price if orig_line else rline.product_id.buying_price
            uom = orig_line.uom_id.id if orig_line and orig_line.uom_id else False
            uom_mult = orig_line.uom_qty_multiplier if orig_line else 1.0

            sale_vals['line_ids'].append((0, 0, {
                'product_id': rline.product_id.id,
                'variant_id': variant.id if variant else False,
                'accepted_qty': rline.qty_returned,
                'rate': rline.rate,
                'cost_price': cost,
                'uom_id': uom,
                'uom_qty_multiplier': uom_mult,
                'tax_ids': [(6, 0, rline.tax_ids.ids)],
            }))
            
        new_return = self.env['havanoposdesk.sale'].create([sale_vals])
        new_return.action_post()
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.sale',
            'res_id': new_return[0].id,
            'view_mode': 'form',
            'target': 'current',
        }


class SaleReturnWizardLine(models.TransientModel):
    _name = 'havanoposdesk.sale.return.wizard.line'
    _description = 'Sale Return Wizard Line'

    wizard_id = fields.Many2one('havanoposdesk.sale.return.wizard', string='Wizard', ondelete='cascade')
    sale_line_id = fields.Many2one('havanoposdesk.sale.line', string='Sale Line', ondelete='cascade')
    product_id = fields.Many2one('havanoposdesk.product', string='Product', readonly=True, ondelete='cascade')
    variant_id = fields.Many2one('havanoposdesk.product.variant', string='Variant', readonly=True)
    qty_sold = fields.Float(string='Qty Sold', readonly=True)
    qty_returned = fields.Float(string='Return Qty', default=0.0)
    rate = fields.Float(string='Rate', readonly=True)
    tax_ids = fields.Many2many('havanoposdesk.tax', string='Taxes', readonly=True)
    price_subtotal = fields.Float(string='Subtotal', compute='_compute_amount')
    price_tax = fields.Float(string='Tax', compute='_compute_amount')
    amount = fields.Float(string='Total', compute='_compute_amount')

    @api.depends('qty_returned', 'rate', 'tax_ids')
    def _compute_amount(self):
        for record in self:
            base_amount = record.qty_returned * record.rate
            taxes = record.tax_ids
            
            inclusive_taxes = taxes.filtered(lambda t: t.is_inclusive)
            exclusive_taxes = taxes.filtered(lambda t: not t.is_inclusive)
            
            rate_incl = sum(inclusive_taxes.mapped('rate')) / 100.0
            rate_excl = sum(exclusive_taxes.mapped('rate')) / 100.0
            
            untaxed_amount = base_amount / (1.0 + rate_incl)
            inclusive_tax_amount = base_amount - untaxed_amount
            exclusive_tax_amount = untaxed_amount * rate_excl
            
            record.price_subtotal = untaxed_amount
            record.price_tax = inclusive_tax_amount + exclusive_tax_amount
            record.amount = record.price_subtotal + record.price_tax
