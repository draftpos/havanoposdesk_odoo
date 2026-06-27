from odoo import models, fields, api
from odoo.exceptions import ValidationError

class PurchaseReturnWizard(models.TransientModel):
    _name = 'havanoposdesk.purchase.return.wizard'
    _description = 'Purchase Return Wizard'

    purchase_id = fields.Many2one('havanoposdesk.purchase', string='Purchase', required=True)
    line_ids = fields.One2many('havanoposdesk.purchase.return.wizard.line', 'wizard_id', string='Items to Return')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_id') and self.env.context.get('active_model') == 'havanoposdesk.purchase':
            purchase = self.env['havanoposdesk.purchase'].browse(self.env.context.get('active_id'))
            res['purchase_id'] = purchase.id
            
            # Calculate already returned quantities per product
            returned_qtys = {}
            for ret in purchase.return_purchase_ids:
                if ret.state != 'cancelled':
                    for rl in ret.line_ids:
                        returned_qtys[rl.product_id.id] = returned_qtys.get(rl.product_id.id, 0.0) + rl.accepted_qty

            lines = []
            for line in purchase.line_ids:
                remaining_qty = line.accepted_qty - returned_qtys.get(line.product_id.id, 0.0)
                if remaining_qty > 0:
                    lines.append((0, 0, {
                        'purchase_line_id': line.id,
                        'product_id': line.product_id.id,
                        'qty_purchased': remaining_qty,
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
        has_existing_returns = any(r.state != 'cancelled' for r in self.purchase_id.return_purchase_ids)
        if has_existing_returns:
            total_remaining = sum(l.qty_purchased for l in self.line_ids)
            total_returning = sum(l.qty_returned for l in self.line_ids)
            if total_returning < total_remaining:
                raise ValidationError("You cannot perform multiple partial returns. Please return all remaining items in a single debit note.")
            
        purchase_vals = {
            'is_return': True,
            'return_id': self.purchase_id.id,
            'supplier': self.purchase_id.supplier.id,
            'store_id': self.purchase_id.store_id.id,
            'tenant_id': self.purchase_id.tenant_id.id,
            'line_ids': [],
        }

        for rline in return_lines:
            if rline.qty_returned > rline.qty_purchased:
                raise ValidationError(f"You cannot return more than what was purchased for {rline.product_id.name}.")
                
            purchase_vals['line_ids'].append((0, 0, {
                'product_id': rline.product_id.id,
                'accepted_qty': rline.qty_returned,
                'rate': rline.rate,
                'tax_ids': [(6, 0, rline.tax_ids.ids)],
            }))
            
        new_return = self.env['havanoposdesk.purchase'].create([purchase_vals])
        new_return.action_post()
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.purchase',
            'res_id': new_return[0].id,
            'view_mode': 'form',
            'target': 'current',
        }


class PurchaseReturnWizardLine(models.TransientModel):
    _name = 'havanoposdesk.purchase.return.wizard.line'
    _description = 'Purchase Return Wizard Line'

    wizard_id = fields.Many2one('havanoposdesk.purchase.return.wizard', string='Wizard')
    purchase_line_id = fields.Many2one('havanoposdesk.purchase.line', string='Purchase Line')
    product_id = fields.Many2one('havanoposdesk.product', string='Product', readonly=True)
    qty_purchased = fields.Float(string='Qty Purchased', readonly=True)
    qty_returned = fields.Float(string='Return Qty', default=0.0)
    rate = fields.Float(string='Rate', readonly=True)
    tax_ids = fields.Many2many('havanoposdesk.tax', string='Taxes', readonly=True)
