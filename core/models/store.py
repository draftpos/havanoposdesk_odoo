from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, RedirectWarning

class HavanoposdeskStore(models.Model):
    _name = 'havanoposdesk.store'
    _description = 'Store'

    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'Store name must be unique per tenant!')
    ]

    name = fields.Char(string='Store Name', required=True)
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    currency_id = fields.Many2one(
        'res.currency', 
        string='Store Currency', 
        default=lambda self: self.env.user.tenant_id.currency_id.id if self.env.user.tenant_id else self.env.ref('base.USD').id
    )
    pricelist_ids = fields.Many2many(
        'havanoposdesk.pricelist',
        'store_pricelist_rel',
        'store_id',
        'pricelist_id',
        string='Allowed Pricelists',
        domain="[('tenant_id', '=', tenant_id), ('type', '=', 'selling')]"
    )
    pricelist_id = fields.Many2one(
        'havanoposdesk.pricelist', 
        string='Default Pricelist',
        domain="[('id', 'in', pricelist_ids)]",
        required=True
    )
    active = fields.Boolean(string='Active', default=True)
    is_default = fields.Boolean(string='Is Default', default=False)
    auto_populate_data = fields.Boolean(
        string='Auto-Populate Data', 
        default=True, 
        help="If checked, existing products, customers, and suppliers will automatically be linked to this new store."
    )


    @api.depends('name', 'tenant_id')
    def _compute_display_name(self):
        is_super_admin = self.env.user.has_group('base.group_system')
        for record in self:
            if is_super_admin and record.tenant_id:
                record.display_name = f"{record.name} ({record.tenant_id.name})"
            else:
                record.display_name = record.name

    @api.constrains('is_default', 'tenant_id')
    def _check_single_default_store(self):
        for store in self:
            if store.is_default:
                domain = [
                    ('tenant_id', '=', store.tenant_id.id),
                    ('is_default', '=', True),
                    ('id', '!=', store.id)
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError("Only one store can be set as the default store per tenant.")

    @api.constrains('pricelist_id', 'pricelist_ids')
    def _check_default_pricelist(self):
        for store in self:
            if store.pricelist_id and store.pricelist_id not in store.pricelist_ids:
                raise ValidationError("The default pricelist must be one of the allowed pricelists.")

    # Computed statistics fields to avoid undefined errors in list view
    terminal_count = fields.Integer(string='Terminals', compute='_compute_store_statistics')
    last_open = fields.Date(string='Last Open', compute='_compute_store_statistics')
    sales_count = fields.Integer(string='Sales Count', compute='_compute_store_statistics')
    purchases_count = fields.Integer(string='Purchases Count', compute='_compute_store_statistics')
    sale_value = fields.Float(string='Sales Value', compute='_compute_store_statistics')
    users_count = fields.Integer(string='Users Count', compute='_compute_store_statistics')

    def _compute_store_statistics(self):
        for store in self:
            # Terminals
            terminals = self.env['havanoposdesk.pos.terminal'].search([('store_id', '=', store.id)])
            store.terminal_count = len(terminals)
            
            # Users
            store.users_count = self.env['res.users'].search_count([('store_ids', 'in', store.id)])
            
            # Sales & Purchases (using store name string)
            sales = self.env['havanoposdesk.sale'].search([('store', '=', store.name)])
            store.sales_count = len(sales)
            store.sale_value = sum(sales.mapped('line_ids.amount'))
            
            purchases = self.env['havanoposdesk.purchase'].search([('store_id', '=', store.id)])
            store.purchases_count = len(purchases)
            
            # Last open (from last sale date)
            if sales:
                last_sale = max(sales, key=lambda s: s.posting_date)
                store.last_open = last_sale.posting_date
            else:
                store.last_open = False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        tenant_id = res.get('tenant_id') or (self.env.user.tenant_id.id if self.env.user.tenant_id else False)
        if tenant_id:
            selling_pricelists = self.env['havanoposdesk.pricelist'].sudo().search([
                ('tenant_id', '=', tenant_id),
                ('type', '=', 'selling')
            ])
            if not selling_pricelists:
                retail_pl = self.env['havanoposdesk.pricelist'].sudo().create({
                    'name': 'Retail',
                    'type': 'selling',
                    'tenant_id': tenant_id
                })
                selling_pricelists = retail_pl

            if 'pricelist_ids' in fields_list and not res.get('pricelist_ids'):
                res['pricelist_ids'] = [(6, 0, selling_pricelists.ids)]
            if 'pricelist_id' in fields_list and not res.get('pricelist_id'):
                retail_pl = selling_pricelists.filtered(lambda p: p.name and 'retail' in p.name.lower())
                res['pricelist_id'] = (retail_pl[0] if retail_pl else selling_pricelists[0]).id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if self.env.user.havano_role == 'super_admin':
                continue
                
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if not tenant_id:
                raise ValidationError('Cannot create a store without an associated tenant.')

            # Ensure default and allowed pricelists are assigned by default
            selling_pricelists = self.env['havanoposdesk.pricelist'].sudo().search([
                ('tenant_id', '=', tenant_id),
                ('type', '=', 'selling')
            ])
            if not selling_pricelists:
                retail_pl = self.env['havanoposdesk.pricelist'].sudo().create({
                    'name': 'Retail',
                    'type': 'selling',
                    'tenant_id': tenant_id
                })
                selling_pricelists = retail_pl

            if not vals.get('pricelist_ids'):
                vals['pricelist_ids'] = [(6, 0, selling_pricelists.ids)]

            if not vals.get('pricelist_id'):
                retail_pl = selling_pricelists.filtered(lambda p: p.name and 'retail' in p.name.lower())
                vals['pricelist_id'] = (retail_pl[0] if retail_pl else selling_pricelists[0]).id
                
            tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
            if tenant.subscription_state != 'active':
                if tenant.subscription_plan_id:
                    raise RedirectWarning(
                        _('Cannot create a store. The tenant subscription is not active.'),
                        {
                            'name': _('Pay & Activate Subscription'),
                            'type': 'ir.actions.act_window',
                            'res_model': 'havanoposdesk.subscription.pay.wizard',
                            'view_mode': 'form',
                            'views': [(False, 'form')],
                            'target': 'new',
                            'context': {
                                'default_tenant_id': tenant.id,
                                'default_subscription_plan_id': tenant.subscription_plan_id.id,
                                'default_amount': tenant.subscription_plan_id.price,
                            }
                        },
                        _('Subscribe Now')
                    )
                else:
                    raise RedirectWarning(
                        _('Cannot create a store. Please pick a subscription plan.'),
                        {
                            'name': _('Select Subscription Plan'),
                            'type': 'ir.actions.act_window',
                            'res_model': 'havanoposdesk.tenant.upgrade.wizard',
                            'view_mode': 'form',
                            'views': [(False, 'form')],
                            'target': 'new',
                            'context': {
                                'default_tenant_id': tenant.id,
                            }
                        },
                        _('Select Plan')
                    )
                
            plan = tenant.subscription_plan_id
            if not plan:
                raise RedirectWarning(
                    _('Please pick a subscription plan to start creating stores.'),
                    {
                        'name': _('Select Subscription Plan'),
                        'type': 'ir.actions.act_window',
                        'res_model': 'havanoposdesk.tenant.upgrade.wizard',
                        'view_mode': 'form',
                        'views': [(False, 'form')],
                        'target': 'new',
                        'context': {
                            'default_tenant_id': tenant.id,
                        }
                    },
                    _('Select Plan')
                )
                
            max_allowed = tenant.effective_max_stores or (plan.max_stores if plan else 0)
            if max_allowed and max_allowed > 0:
                current = self.search_count([('tenant_id', '=', tenant.id)])
                if current >= max_allowed:
                    raise RedirectWarning(
                        _('Maximum number of stores (%s) reached for this subscription plan.') % max_allowed,
                        {
                            'name': _('Select Subscription Plan'),
                            'type': 'ir.actions.act_window',
                            'res_model': 'havanoposdesk.tenant.upgrade.wizard',
                            'view_mode': 'form',
                            'views': [(False, 'form')],
                            'target': 'new',
                            'context': {
                                'default_tenant_id': tenant.id,
                            }
                        },
                        _('Upgrade Subscription')
                    )
                    
            # Ensure the tenant_id is correctly forced
            vals['tenant_id'] = tenant_id

        # Use sudo() to bypass record rules during creation, 
        # since the new store isn't in the user's store_ids yet.
        stores = super(HavanoposdeskStore, self.sudo()).create(vals_list)
        
        if stores:
            # Always auto-assign new stores to ALL active admin users of the tenant.
            # This ensures:
            # - Super Admin creating a store: tenant admins see it immediately on login
            # - Tenant Admin creating a store: all their fellow admins see it too
            for store in stores:
                if store.tenant_id:
                    tenant_admins = self.env['res.users'].sudo().search([
                        ('tenant_id', '=', store.tenant_id.id),
                        ('havano_role', '=', 'admin'),
                        ('active', '=', True),
                    ])
                    if tenant_admins:
                        for admin in tenant_admins:
                            write_vals = {'store_ids': [(4, store.id)]}
                            if not admin.default_store_id:
                                write_vals['default_store_id'] = store.id
                            if not admin.pricelist_id and store.pricelist_id:
                                write_vals['pricelist_id'] = store.pricelist_id.id
                            admin.sudo().write(write_vals)
                    
                    # Auto-Populate Logic
                    if store.auto_populate_data:
                        # 1. Add store to all existing products for the tenant
                        products = self.env['havanoposdesk.product'].sudo().search([('tenant_id', '=', store.tenant_id.id)])
                        if products:
                            products.write({'store_ids': [(4, store.id)]})
                            
                        # 2. Add store to all existing customers for the tenant
                        customers = self.env['havanoposdesk.customer'].sudo().search([('tenant_id', '=', store.tenant_id.id)])
                        if customers:
                            customers.write({'store_ids': [(4, store.id)]})
            
        return stores


    def write(self, vals):
        """
        Override write() to cascade a store name change to every table that
        stores the store name as a denormalised Char column.

        Tables updated automatically on rename:
          - havanoposdesk_sale              (store Char)
          - havanoposdesk_stock_valuation   (store Char + store_id FK)
          - havanoposdesk_stock_ledger      (store Char + store_id FK)
          - havanoposdesk_stock_entry       (from_warehouse / to_warehouse Char)
          - havanoposdesk_stock_entry_line  (store Char)
          - havanoposdesk_stock_adjustment_line (store Char)
          - havanoposdesk_purchase_line     (store Char)
        """
        new_name = vals.get('name')

        if new_name:
            # Snapshot old names before the ORM write changes them
            old_names = {store.id: store.name for store in self}

        result = super().write(vals)

        if new_name:
            for store in self:
                old_name = old_names.get(store.id)
                if old_name and old_name != new_name:
                    self._cascade_store_rename(old_name, new_name, store.id, store.tenant_id.id)

        return result

    def _cascade_store_rename(self, old_name, new_name, store_id, tenant_id):
        """Run raw SQL to update all denormalised store-name columns in one pass."""
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(
            "Havano: cascading store rename '%s' -> '%s' (store_id=%s, tenant_id=%s)",
            old_name, new_name, store_id, tenant_id
        )
        cr = self.env.cr

        # 1. havanoposdesk_sale
        cr.execute(
            "UPDATE havanoposdesk_sale SET store = %s WHERE store = %s AND tenant_id = %s",
            (new_name, old_name, tenant_id)
        )
        _logger.info("  sale: %s rows", cr.rowcount)

        # 2. havanoposdesk_stock_valuation (Char + FK)
        cr.execute(
            """UPDATE havanoposdesk_stock_valuation
                  SET store = %s, store_id = %s
                WHERE store = %s AND tenant_id = %s""",
            (new_name, store_id, old_name, tenant_id)
        )
        _logger.info("  stock_valuation: %s rows", cr.rowcount)

        # 3. havanoposdesk_stock_ledger (Char + FK)
        cr.execute(
            """UPDATE havanoposdesk_stock_ledger
                  SET store = %s, store_id = %s
                WHERE store = %s AND tenant_id = %s""",
            (new_name, store_id, old_name, tenant_id)
        )
        _logger.info("  stock_ledger: %s rows", cr.rowcount)

        # Clear cache so Odoo picks up the updated database values
        self.env.invalidate_all()
        self.env.registry.clear_cache()

        _logger.info("Havano: store rename cascade complete.")
