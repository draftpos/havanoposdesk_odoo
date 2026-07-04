# -*- coding: utf-8 -*-
from odoo import models, fields

class HavanoposdeskSupportTicket(models.Model):
    _name = 'havanoposdesk.support.ticket'
    _description = 'Havano POS Support Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Subject', required=True, tracking=True)
    description = fields.Text(string='Description', required=True)
    email = fields.Char(string='Contact Email', tracking=True)
    phone = fields.Char(string='Contact Phone', tracking=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', tracking=True)
    user_id = fields.Many2one('res.users', string='Submitter', tracking=True)
    status = fields.Selection([
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved')
    ], string='Status', default='new', tracking=True)
