# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class PosPriceApprovalRequest(models.Model):
    _name = 'pos.price.approval.request'
    _table = 'pos_price_approvals'
    _inherit = ['havanoposdesk.audit.mixin']
    _description = 'POS Price Change Approval'
    _order = 'create_date desc, id desc'

    request_code = fields.Char(string='Request ID', index=True, copy=False)
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1).id if self.env.user.havano_role == 'super_admin' else False),
        index=True
    )
    store_id = fields.Many2one('havanoposdesk.store', string='Store', index=True)
    pos_profile = fields.Char(string='POS Profile / Terminal', index=True)
    terminal_id = fields.Char(string='Terminal ID', index=True)
    
    cashier_id = fields.Many2one('res.users', string='Cashier', required=True, default=lambda self: self.env.user, index=True)
    cashier_name = fields.Char(string='Cashier Name')
    
    product_id = fields.Many2one('havanoposdesk.product', string='Product', index=True)
    product_id_str = fields.Char(string='Product Ref / ID', index=True)
    product_name = fields.Char(string='Product Name', required=True)
    
    currency_id = fields.Many2one(
        'res.currency', 
        string='Currency', 
        default=lambda self: self.env.user.tenant_id.currency_id.id if self.env.user.tenant_id and self.env.user.tenant_id.currency_id else self.env.ref('base.USD').id
    )
    quantity = fields.Float(string='Quantity', default=1.0)
    original_price = fields.Monetary(string='Original Price', currency_field='currency_id', required=True)
    requested_price = fields.Monetary(string='Requested Price', currency_field='currency_id', required=True)
    counter_price = fields.Monetary(string='Counter-Offer Price', currency_field='currency_id')
    approved_price = fields.Monetary(string='Approved Price', currency_field='currency_id')
    
    difference_amount = fields.Monetary(string='Difference', currency_field='currency_id', compute='_compute_differences', store=True)
    difference_percent = fields.Float(string='Difference %', compute='_compute_differences', store=True)
    
    status = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('counter_offer', 'Counter-Offer'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ], string='Status', default='pending', required=True, index=True)
    
    note = fields.Text(string='Note / Rejection Reason')
    reviewed_by = fields.Many2one('res.users', string='Reviewed By', readonly=True)
    reviewed_by_name = fields.Char(string='Reviewed By Name', compute='_compute_reviewed_by_name', store=True)
    
    created_at = fields.Datetime(string='Requested At', default=fields.Datetime.now, readonly=True)
    updated_at = fields.Datetime(string='Updated At', default=fields.Datetime.now, readonly=True)

    @api.depends('original_price', 'requested_price')
    def _compute_differences(self):
        for rec in self:
            diff = (rec.requested_price or 0.0) - (rec.original_price or 0.0)
            rec.difference_amount = diff
            if rec.original_price and rec.original_price > 0:
                rec.difference_percent = round((diff / rec.original_price) * 100.0, 2)
            else:
                rec.difference_percent = 0.0

    @api.depends('reviewed_by')
    def _compute_reviewed_by_name(self):
        for rec in self:
            rec.reviewed_by_name = rec.reviewed_by.name if rec.reviewed_by else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('tenant_id') and self.env.user.tenant_id:
                vals['tenant_id'] = self.env.user.tenant_id.id
            if vals.get('cashier_id') and not vals.get('cashier_name'):
                cashier = self.env['res.users'].sudo().browse(vals['cashier_id'])
                if cashier.exists():
                    vals['cashier_name'] = cashier.name
            if vals.get('product_id') and not vals.get('product_name'):
                prod = self.env['havanoposdesk.product'].sudo().browse(vals['product_id'])
                if prod.exists():
                    vals['product_name'] = prod.name
        records = super().create(vals_list)
        for rec in records:
            if not rec.request_code:
                rec.request_code = f"appr_{rec.id}"
            rec._notify_backoffice_new_request()
        return records

    def action_approve(self, approved_price=None, note=None):
        self.ensure_one()
        if self.status != 'pending':
            raise UserError(_("This request is already resolved (Status: %s).") % self.status)
        price = approved_price if approved_price is not None else self.requested_price
        self.write({
            'status': 'approved',
            'approved_price': price,
            'note': note or self.note or _("Approved by Manager"),
            'reviewed_by': self.env.user.id,
            'updated_at': fields.Datetime.now(),
        })
        self._notify_pos_resolved()
        return True

    def action_reject(self, note=None):
        self.ensure_one()
        if self.status != 'pending':
            raise UserError(_("This request is already resolved (Status: %s).") % self.status)
        self.write({
            'status': 'rejected',
            'note': note or self.note or _("Rejected by Manager"),
            'reviewed_by': self.env.user.id,
            'updated_at': fields.Datetime.now(),
        })
        self._notify_pos_resolved()
        return True

    def action_counter_offer(self, counter_price, note=None):
        self.ensure_one()
        if self.status != 'pending':
            raise UserError(_("This request is already resolved (Status: %s).") % self.status)
        self.write({
            'status': 'counter_offer',
            'counter_price': counter_price,
            'approved_price': counter_price,
            'note': note or self.note or _("Manager counter-offer"),
            'reviewed_by': self.env.user.id,
            'updated_at': fields.Datetime.now(),
        })
        self._notify_pos_resolved()
        return True

    def action_cancel(self):
        for rec in self:
            if rec.status == 'pending':
                rec.write({
                    'status': 'cancelled',
                    'updated_at': fields.Datetime.now(),
                })
        return True

    def _notify_backoffice_new_request(self):
        try:
            payload = {
                'request_id': self.request_code or f"appr_{self.id}",
                'product_name': self.product_name,
                'cashier': self.cashier_name or (self.cashier_id.name if self.cashier_id else ''),
                'pos_profile': self.pos_profile or '',
                'original_price': self.original_price,
                'requested_price': self.requested_price,
                'quantity': self.quantity,
                'difference_percent': self.difference_percent,
                'note': self.note or '',
                'created_at': fields.Datetime.to_string(self.created_at) if self.created_at else ''
            }
            if hasattr(self.env['bus.bus'], '_sendone'):
                channels = [
                    f"tenant:{self.tenant_id.id}",
                    f"tenant_{self.tenant_id.id}",
                    "pos_price_approvals"
                ]
                for ch in channels:
                    try:
                        self.env['bus.bus'].sudo()._sendone(ch, 'new_price_approval_request', payload)
                        self.env['bus.bus'].sudo()._sendone(ch, 'pos:new_price_approval_request', payload)
                    except Exception:
                        pass
        except Exception as e:
            _logger.warning("Could not send bus notification for new price approval %s: %s", self.id, e)

    def _notify_pos_resolved(self):
        try:
            payload = {
                'request_id': self.request_code or f"appr_{self.id}",
                'status': self.status,
                'approved_price': self.approved_price,
                'counter_price': self.counter_price,
                'note': self.note or (f"Approved by {self.reviewed_by.name}" if self.status == 'approved' and self.reviewed_by else '')
            }
            if hasattr(self.env['bus.bus'], '_sendone'):
                channels = [
                    f"tenant:{self.tenant_id.id}",
                    f"tenant_{self.tenant_id.id}",
                    f"pos:{self.cashier_id.id}" if self.cashier_id else None,
                    f"terminal_{self.terminal_id}" if self.terminal_id else None,
                    f"terminal:{self.terminal_id}" if self.terminal_id else None,
                ]
                for ch in filter(None, channels):
                    try:
                        self.env['bus.bus'].sudo()._sendone(ch, 'pos:price_approval_resolved', payload)
                        self.env['bus.bus'].sudo()._sendone(ch, 'price_approval_resolved', payload)
                    except Exception:
                        pass
        except Exception as e:
            _logger.warning("Could not send bus notification for resolved price approval %s: %s", self.id, e)
