from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, RedirectWarning

class HavanoposdeskStore(models.Model):
    _name = 'havanoposdesk.store'
    _description = 'Store'

    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'Store name must be unique per tenant!')
    ]

    name = fields.Char(string='Store Name', required=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True)
    currency_id = fields.Many2one(
        'res.currency', 
        string='Store Currency', 
        default=lambda self: self.env.user.tenant_id.currency_id.id if self.env.user.tenant_id else self.env.ref('base.USD').id
    )
    active = fields.Boolean(string='Active', default=True)
    is_default = fields.Boolean(string='Is Default', default=False)

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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if self.env.user.havano_role == 'super_admin':
                continue
                
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if not tenant_id:
                raise ValidationError('Cannot create a store without an associated tenant.')
                
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
                
            if plan.max_stores and plan.max_stores > 0:
                current = self.search_count([('tenant_id', '=', tenant.id)])
                if current >= plan.max_stores:
                    raise RedirectWarning(
                        _('Maximum number of stores (%s) reached for this subscription plan.') % plan.max_stores,
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

        return super().create(vals_list)

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
            "Havano: cascading store rename '%s' → '%s' (store_id=%s, tenant_id=%s)",
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

        # 4a. havanoposdesk_stock_entry — from_warehouse
        cr.execute(
            """UPDATE havanoposdesk_stock_entry
                  SET from_warehouse = %s
                WHERE from_warehouse = %s AND tenant_id = %s""",
            (new_name, old_name, tenant_id)
        )
        _logger.info("  stock_entry (from_warehouse): %s rows", cr.rowcount)

        # 4b. havanoposdesk_stock_entry — to_warehouse
        cr.execute(
            """UPDATE havanoposdesk_stock_entry
                  SET to_warehouse = %s
                WHERE to_warehouse = %s AND tenant_id = %s""",
            (new_name, old_name, tenant_id)
        )
        _logger.info("  stock_entry (to_warehouse): %s rows", cr.rowcount)

        # 5. havanoposdesk_stock_entry_line — scoped via parent entry
        cr.execute(
            """UPDATE havanoposdesk_stock_entry_line sl
                  SET store = %s
                 FROM havanoposdesk_stock_entry se
                WHERE sl.stock_entry_id = se.id
                  AND sl.store = %s
                  AND se.tenant_id = %s""",
            (new_name, old_name, tenant_id)
        )
        _logger.info("  stock_entry_line: %s rows", cr.rowcount)

        # 6. havanoposdesk_stock_adjustment_line — scoped via parent adjustment
        cr.execute(
            """UPDATE havanoposdesk_stock_adjustment_line sal
                  SET store = %s
                 FROM havanoposdesk_stock_adjustment sa
                WHERE sal.adjustment_id = sa.id
                  AND sal.store = %s
                  AND sa.tenant_id = %s""",
            (new_name, old_name, tenant_id)
        )
        _logger.info("  stock_adjustment_line: %s rows", cr.rowcount)

        # 7. havanoposdesk_purchase_line — scoped via parent purchase
        cr.execute(
            """UPDATE havanoposdesk_purchase_line pl
                  SET store = %s
                 FROM havanoposdesk_purchase p
                WHERE pl.purchase_id = p.id
                  AND pl.store = %s
                  AND p.tenant_id = %s""",
            (new_name, old_name, tenant_id)
        )
        _logger.info("  purchase_line: %s rows", cr.rowcount)

        _logger.info("Havano: store rename cascade complete.")

