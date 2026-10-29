# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class PosPriceApprovalWizard(models.TransientModel):
    _name = 'pos.price.approval.wizard'
    _description = 'POS Price Approval Action Wizard'

    request_id = fields.Many2one('pos.price.approval.request', string='Approval Request', required=True, ondelete='cascade')
    action_type = fields.Selection([
        ('reject', 'Reject'),
        ('counter_offer', 'Counter-Offer')
    ], string='Action', required=True)
    
    currency_id = fields.Many2one('res.currency', related='request_id.currency_id')
    original_price = fields.Monetary(related='request_id.original_price', string='Original Price', readonly=True)
    requested_price = fields.Monetary(related='request_id.requested_price', string='Requested Price', readonly=True)
    
    counter_price = fields.Monetary(string='Counter Price', currency_field='currency_id')
    note = fields.Text(string='Note / Reason', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id and self.env.context.get('active_model') == 'pos.price.approval.request':
            res['request_id'] = active_id
        if self.env.context.get('default_action_type'):
            res['action_type'] = self.env.context.get('default_action_type')
        return res

    def action_confirm(self):
        self.ensure_one()
        if self.action_type == 'reject':
            self.request_id.action_reject(note=self.note)
        elif self.action_type == 'counter_offer':
            if not self.counter_price or self.counter_price <= 0:
                raise ValidationError(_("Please provide a valid counter-offer price greater than zero."))
            self.request_id.action_counter_offer(counter_price=self.counter_price, note=self.note)
        return {'type': 'ir.actions.act_window_close'}
