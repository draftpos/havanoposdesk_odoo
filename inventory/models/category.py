import odoo
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HavanoposdeskCategory(models.Model):
    _name = 'havanoposdesk.category'
    _description = 'Category / Item Group'
    _parent_name = "parent_id"
    _parent_store = True
    _rec_name = 'complete_name'
    _order = 'complete_name, id'

    name = fields.Char(string='Category Name', required=True)
    complete_name = fields.Char(
        string='Complete Name', 
        compute='_compute_complete_name', 
        recursive=True, 
        store=True
    )
    parent_id = fields.Many2one(
        'havanoposdesk.category', 
        string='Parent Sub-Unit / Group', 
        index=True, 
        ondelete='cascade',
        domain="[('tenant_id', '=', tenant_id), ('id', '!=', id)]"
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        'havanoposdesk.category', 
        'parent_id', 
        string='Sub-Categories'
    )
    is_sub_unit = fields.Boolean(
        string='Is Sub-Unit / Business Line', 
        default=False, 
        help="Mark as true if this represents a high-level business line or station department (e.g. Fuel, Kiosk, Spare Parts, Gas)."
    )
    not_for_pos = fields.Boolean(string='Not For POS', default=False)
    store_ids = fields.Many2many(
        'havanoposdesk.store', 
        string='Stores', 
        required=False, 
        default=lambda self: self._default_store_ids()
    )
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self._default_tenant_id()
    )

    products_count = fields.Integer(string='Products Count', compute='_compute_products_count')
    child_count = fields.Integer(string='Sub-Categories Count', compute='_compute_child_count')

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for record in self:
            if record.parent_id:
                record.complete_name = f"{record.parent_id.complete_name or record.parent_id.name} / {record.name}"
            else:
                record.complete_name = record.name

    @api.depends('complete_name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.complete_name or record.name

    def _compute_products_count(self):
        for record in self:
            all_cat_ids = self.sudo().search([('id', 'child_of', record.id)]).ids
            record.products_count = self.env['havanoposdesk.product'].sudo().search_count([
                ('category_id', 'in', all_cat_ids)
            ])

    def _compute_child_count(self):
        for record in self:
            record.child_count = len(record.child_ids)

    def _get_descendants(self):
        """Recursively fetch all descendant sub-categories."""
        self.ensure_one()
        return self.search([('id', 'child_of', self.id), ('id', '!=', self.id)])

    @api.constrains('parent_id')
    def _check_category_recursion(self):
        if not self._check_recursion():
            raise ValidationError(_("You cannot create recursive Item Groups / Categories."))

    @api.constrains('name', 'tenant_id', 'parent_id')
    def _check_unique_name(self):
        for record in self:
            if record.name and record.tenant_id:
                domain = [
                    ('id', '!=', record.id),
                    ('tenant_id', '=', record.tenant_id.id),
                    ('parent_id', '=', record.parent_id.id if record.parent_id else False),
                    ('name', '=ilike', record.name.strip())
                ]
                if self.sudo().search_count(domain) > 0:
                    parent_label = f" under '{record.parent_id.name}'" if record.parent_id else ""
                    raise ValidationError(f"A Category with the name '{record.name}' already exists{parent_label}. Please choose a different name.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('tenant_id') and self.env.user.tenant_id:
                vals['tenant_id'] = self.env.user.tenant_id.id
        return super().create(vals_list)

    def _default_store_ids(self):
        if self.env.registry.ready and self.env.user.default_store_id:
            return [(6, 0, [self.env.user.default_store_id.id])]
        return False

    def _default_tenant_id(self):
        if self.env.registry.ready:
            return self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
        return False

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        if self.env.context.get('import_file') and operator == '=':
            operator = 'ilike'
        return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

    def action_view_products(self):
        self.ensure_one()
        all_cat_ids = self.search([('id', 'child_of', self.id)]).ids
        return {
            'name': _('Products in %s') % (self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.product',
            'view_mode': 'list,form',
            'domain': [('category_id', 'in', all_cat_ids)],
            'context': {'default_category_id': self.id, 'default_tenant_id': self.tenant_id.id},
        }

    def action_view_sub_categories(self):
        self.ensure_one()
        return {
            'name': _('Sub-Categories of %s') % (self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.category',
            'view_mode': 'list,form',
            'domain': [('parent_id', '=', self.id)],
            'context': {'default_parent_id': self.id, 'default_tenant_id': self.tenant_id.id},
        }
