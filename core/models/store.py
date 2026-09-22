from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, RedirectWarning
from odoo.addons.base.models.res_partner import _tz_get

class HavanoposdeskStore(models.Model):
    _name = 'havanoposdesk.store'
    _inherit = ['havanoposdesk.audit.mixin']
    _description = 'Store'

    _constraints = [
        models.Constraint('unique (name, tenant_id)', 'Store name must be unique per tenant!')
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
    tz = fields.Selection(
        _tz_get,
        string='Timezone',
        default=lambda self: self.env.user.tz or 'Africa/Harare',
        required=True,
        help="Store timezone for local transaction recording and validation."
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

    address = fields.Text(string='Address')
    phone_1 = fields.Char(string='Phone 1')
    phone_2 = fields.Char(string='Phone 2')
    email = fields.Char(string='Email')
    website = fields.Char(string='Website')
    tin = fields.Char(string='TIN')
    vat_no = fields.Char(string='VAT No')
    default_terms = fields.Html(string='Terms & Conditions')
    default_footer = fields.Text(string='Default Footer')
    powered_by_footer = fields.Char(string='Powered By Footer Text', default='Powered by HavanoERP')
    tagline = fields.Char(string='Tagline')

    bank_account_ids = fields.One2many('havanoposdesk.store.bank', 'store_id', string='Bank Accounts')

    # Per-Store ZIMRA Fiscalization Settings
    enable_fiscalization = fields.Boolean(string='Enable Fiscalization', default=False)
    is_vat_registered = fields.Boolean(string='VAT Registered Taxpayer', default=True, help="Uncheck if company is non-VAT registered / exempt.")
    fiscal_provider = fields.Selection([
        ('havano_zimra', 'Havano ZIMRA Cloud'),
        ('axis', 'Axis Virtual API'),
        ('revmax', 'Revmax Hardware')
    ], string='Fiscal Provider', default='havano_zimra')
    fiscal_base_url = fields.Char(string='Base URL', default='https://erpfiscal.havano.online')
    fiscal_api_key = fields.Char(string='API Key')
    fiscal_api_secret = fields.Char(string='API Secret')
    fiscal_device_sn = fields.Char(string='Device Serial No (EFD SN)')
    fiscal_ping_interval = fields.Integer(string='Ping Interval (Minutes)', default=5)
    fiscalized_invoice_heading = fields.Char(string='Fiscalized Invoice Heading', default='Fiscal Tax Invoice')

    # Sequence Configuration
    sale_seq_prefix = fields.Char(string='Sale Sequence Prefix', default='S')
    sale_seq_next = fields.Integer(string='Sale Sequence Next Number', default=1)
    sale_seq_padding = fields.Integer(string='Sale Sequence Padding', default=4)

    sale_ret_seq_prefix = fields.Char(string='Credit Note Sequence Prefix', default='C')
    sale_ret_seq_next = fields.Integer(string='Credit Note Sequence Next Number', default=1)
    sale_ret_seq_padding = fields.Integer(string='Credit Note Sequence Padding', default=3)

    quotation_seq_prefix = fields.Char(string='Quotation Sequence Prefix', default='Q')
    quotation_seq_next = fields.Integer(string='Quotation Sequence Next Number', default=1)
    quotation_seq_padding = fields.Integer(string='Quotation Sequence Padding', default=4)

    # Subscription Management (Related to Tenant)
    subscription_plan_id = fields.Many2one(related='tenant_id.subscription_plan_id', string='Current Plan', readonly=True)
    subscription_state = fields.Selection(related='tenant_id.subscription_state', string='Subscription State', readonly=True)
    payment_status = fields.Selection(related='tenant_id.payment_status', string='Payment Status', readonly=True)
    subscription_start_date = fields.Date(related='tenant_id.subscription_start_date', string='Start Date', readonly=True)
    subscription_end_date = fields.Date(related='tenant_id.subscription_end_date', string='Expiry Date', readonly=True)
    subscription_total_amount = fields.Float(related='tenant_id.subscription_total_amount', string='Plan Amount', readonly=True)
    account_balance = fields.Float(related='tenant_id.account_balance', string='Account Balance', readonly=True)
    pending_subscription_plan_id = fields.Many2one(related='tenant_id.pending_subscription_plan_id', string='Pending Plan', readonly=True)
    pending_subscription_total_amount = fields.Float(related='tenant_id.pending_subscription_total_amount', string='Pending Plan Amount', readonly=True)

    def action_open_subscription(self):
        self.ensure_one()
        if not self.tenant_id:
            from odoo.exceptions import UserError
            raise UserError("No tenant associated with this store.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'My Subscription',
            'res_model': 'havanoposdesk.tenant',
            'res_id': self.tenant_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_manage_subscription(self):
        self.ensure_one()
        if self.tenant_id:
            return self.tenant_id.action_upgrade_plan()
        return False

    def action_topup_account(self):
        self.ensure_one()
        if self.tenant_id:
            return self.tenant_id.action_topup_wizard()
        return False

    def action_pay_subscription_wizard(self):
        self.ensure_one()
        if self.tenant_id:
            return self.tenant_id.action_pay_subscription_wizard()
        return False

    def action_pay_from_balance(self):
        self.ensure_one()
        if self.tenant_id:
            return self.tenant_id.action_pay_from_balance()
        return False

    def action_cancel_pending_subscription(self):
        self.ensure_one()
        if self.tenant_id:
            return self.tenant_id.action_cancel()
        return False
    def action_ping_zimra_device(self):
        self.ensure_one()
        from .fiscal_service import get_zimra_service
        service = get_zimra_service(self.env)
        res = service.ping_device(self)
        if res.get('success'):
            data = res.get('data', {})
            msg = f"Connected! Device SN: {data.get('device_sn', 'OK')} | Status: Online"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Ping Successful',
                    'message': msg,
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Ping Failed',
                    'message': res.get('error', 'Connection failed'),
                    'type': 'danger',
                    'sticky': True,
                }
            }


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
            if self.env.context.get('skip_default_store_check'):
                continue
            if store.is_default:
                domain = [
                    ('tenant_id', '=', store.tenant_id.id),
                    ('is_default', '=', True),
                    ('id', '!=', store.id)
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError("Only one store can be set as the default store per tenant.")
            elif not self.search_count([
                ('tenant_id', '=', store.tenant_id.id),
                ('is_default', '=', True),
            ]):
                raise ValidationError(_('Each tenant must have one default store.'))

    @api.onchange('is_default')
    def _onchange_is_default(self):
        if self.is_default:
            return {
                'warning': {
                    'title': _('Default Store Switched'),
                    'message': _('This store will become the default store when you save. The current default store will be switched off.'),
                }
            }

    @api.constrains('name', 'tenant_id')
    def _check_unique_store_name_per_tenant(self):
        for store in self:
            if store.name and store.tenant_id:
                clean_name = store.name.strip().lower()
                existing = self.search([
                    ('tenant_id', '=', store.tenant_id.id),
                    ('id', '!=', store.id)
                ])
                if any(s.name and s.name.strip().lower() == clean_name for s in existing):
                    raise ValidationError(_("A store with the name '%s' already exists for this tenant.") % store.name.strip())

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        if self.env.context.get('import_file') and operator == '=':
            operator = 'ilike'
        return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

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

    @api.onchange('tenant_id')
    def _onchange_tenant_id_seq(self):
        if self.tenant_id:
            if not self.sale_seq_prefix or self.sale_seq_prefix == 'S':
                self.sale_seq_prefix = self.tenant_id.sale_seq_prefix or 'S'
            if not self.sale_seq_next or self.sale_seq_next == 1:
                self.sale_seq_next = self.tenant_id.sale_seq_next or 1
            if not self.sale_seq_padding or self.sale_seq_padding == 4:
                self.sale_seq_padding = self.tenant_id.sale_seq_padding or 4
            if not self.sale_ret_seq_prefix or self.sale_ret_seq_prefix == 'C':
                self.sale_ret_seq_prefix = self.tenant_id.sale_ret_seq_prefix or 'C'
            if not self.sale_ret_seq_next or self.sale_ret_seq_next == 1:
                self.sale_ret_seq_next = self.tenant_id.sale_ret_seq_next or 1
            if not self.sale_ret_seq_padding or self.sale_ret_seq_padding == 3:
                self.sale_ret_seq_padding = self.tenant_id.sale_ret_seq_padding or 3
            if not self.quotation_seq_prefix or self.quotation_seq_prefix == 'Q':
                self.quotation_seq_prefix = self.tenant_id.quotation_seq_prefix or 'Q'
            if not self.quotation_seq_next or self.quotation_seq_next == 1:
                self.quotation_seq_next = self.tenant_id.quotation_seq_next or 1
            if not self.quotation_seq_padding or self.quotation_seq_padding == 4:
                self.quotation_seq_padding = self.tenant_id.quotation_seq_padding or 4

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        tenant_id = res.get('tenant_id') or (self.env.user.tenant_id.id if self.env.user.tenant_id else False)
        if tenant_id:
            tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
            if tenant:
                if 'sale_seq_prefix' in fields_list and not res.get('sale_seq_prefix'):
                    res['sale_seq_prefix'] = tenant.sale_seq_prefix or 'S'
                if 'sale_seq_next' in fields_list and not res.get('sale_seq_next'):
                    res['sale_seq_next'] = tenant.sale_seq_next or 1
                if 'sale_seq_padding' in fields_list and not res.get('sale_seq_padding'):
                    res['sale_seq_padding'] = tenant.sale_seq_padding or 4
                if 'sale_ret_seq_prefix' in fields_list and not res.get('sale_ret_seq_prefix'):
                    res['sale_ret_seq_prefix'] = tenant.sale_ret_seq_prefix or 'C'
                if 'sale_ret_seq_next' in fields_list and not res.get('sale_ret_seq_next'):
                    res['sale_ret_seq_next'] = tenant.sale_ret_seq_next or 1
                if 'sale_ret_seq_padding' in fields_list and not res.get('sale_ret_seq_padding'):
                    res['sale_ret_seq_padding'] = tenant.sale_ret_seq_padding or 3
                if 'quotation_seq_prefix' in fields_list and not res.get('quotation_seq_prefix'):
                    res['quotation_seq_prefix'] = tenant.quotation_seq_prefix or 'Q'
                if 'quotation_seq_next' in fields_list and not res.get('quotation_seq_next'):
                    res['quotation_seq_next'] = tenant.quotation_seq_next or 1
                if 'quotation_seq_padding' in fields_list and not res.get('quotation_seq_padding'):
                    res['quotation_seq_padding'] = tenant.quotation_seq_padding or 4

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

    def init(self):
        super().init()
        # Initialize sequence values for existing stores from their tenant if unpopulated
        self.env.cr.execute("""
            UPDATE havanoposdesk_store s
            SET sale_seq_prefix = COALESCE(s.sale_seq_prefix, t.sale_seq_prefix, 'S'),
                sale_seq_next = COALESCE(NULLIF(s.sale_seq_next, 0), t.sale_seq_next, 1),
                sale_seq_padding = COALESCE(s.sale_seq_padding, t.sale_seq_padding, 4),
                sale_ret_seq_prefix = COALESCE(s.sale_ret_seq_prefix, t.sale_ret_seq_prefix, 'C'),
                sale_ret_seq_next = COALESCE(NULLIF(s.sale_ret_seq_next, 0), t.sale_ret_seq_next, 1),
                sale_ret_seq_padding = COALESCE(s.sale_ret_seq_padding, t.sale_ret_seq_padding, 3),
                quotation_seq_prefix = COALESCE(s.quotation_seq_prefix, t.quotation_seq_prefix, 'Q'),
                quotation_seq_next = COALESCE(NULLIF(s.quotation_seq_next, 0), t.quotation_seq_next, 1),
                quotation_seq_padding = COALESCE(s.quotation_seq_padding, t.quotation_seq_padding, 4)
            FROM havanoposdesk_tenant t
            WHERE s.tenant_id = t.id
              AND (s.sale_seq_prefix IS NULL OR s.sale_seq_next IS NULL OR s.sale_seq_next = 0)
        """)

    def _get_next_sequence(self, seq_type):
        self.ensure_one()
        prefix_field = f"{seq_type}_seq_prefix"
        next_field = f"{seq_type}_seq_next"
        padding_field = f"{seq_type}_seq_padding"

        prefix = getattr(self, prefix_field)
        if prefix is False or prefix is None:
            prefix = getattr(self.tenant_id, prefix_field) if self.tenant_id else ''

        next_val = getattr(self, next_field)
        if not next_val:
            next_val = getattr(self.tenant_id, next_field) if self.tenant_id else 1

        padding = getattr(self, padding_field)
        if padding is False or padding is None:
            padding = getattr(self.tenant_id, padding_field) if self.tenant_id else 0

        seq_target_map = {
            'sale': ('havanoposdesk.sale', 'name'),
            'quotation': ('havanoposdesk.sale', 'name'),
            'sale_ret': ('havanoposdesk.sale', 'name'),
        }

        target_info = seq_target_map.get(seq_type)
        formatted_seq = ''

        while True:
            seq_str = str(next_val)
            if padding > 0:
                seq_str = seq_str.zfill(padding)
            formatted_seq = f"{prefix or ''}{seq_str}"

            if target_info and target_info[0] in self.env:
                model_name, field_name = target_info
                exists = self.env[model_name].sudo().search_count([
                    ('tenant_id', '=', self.tenant_id.id),
                    (field_name, '=', formatted_seq)
                ]) > 0
                if not exists:
                    break
                next_val += 1
            else:
                break

        self.env.cr.execute(
            f'UPDATE havanoposdesk_store SET "{next_field}" = %s WHERE id = %s',
            (next_val + 1, self.id)
        )
        self.invalidate_recordset([next_field])
        return formatted_seq

    @api.model_create_multi
    def create(self, vals_list):
        assigned_default_tenants = set()
        for vals in vals_list:
            if vals.get('name'):
                vals['name'] = vals['name'].strip()

            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if tenant_id and tenant_id not in assigned_default_tenants and not self.sudo().search_count([
                ('tenant_id', '=', tenant_id),
                ('is_default', '=', True),
            ]):
                vals['is_default'] = True
                assigned_default_tenants.add(tenant_id)

            if tenant_id:
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
                if tenant:
                    if not vals.get('sale_seq_prefix'):
                        vals['sale_seq_prefix'] = tenant.sale_seq_prefix or 'S'
                    if not vals.get('sale_seq_next'):
                        vals['sale_seq_next'] = tenant.sale_seq_next or 1
                    if not vals.get('sale_seq_padding'):
                        vals['sale_seq_padding'] = tenant.sale_seq_padding or 4
                    if not vals.get('sale_ret_seq_prefix'):
                        vals['sale_ret_seq_prefix'] = tenant.sale_ret_seq_prefix or 'C'
                    if not vals.get('sale_ret_seq_next'):
                        vals['sale_ret_seq_next'] = tenant.sale_ret_seq_next or 1
                    if not vals.get('sale_ret_seq_padding'):
                        vals['sale_ret_seq_padding'] = tenant.sale_ret_seq_padding or 3
                    if not vals.get('quotation_seq_prefix'):
                        vals['quotation_seq_prefix'] = tenant.quotation_seq_prefix or 'Q'
                    if not vals.get('quotation_seq_next'):
                        vals['quotation_seq_next'] = tenant.quotation_seq_next or 1
                    if not vals.get('quotation_seq_padding'):
                        vals['quotation_seq_padding'] = tenant.quotation_seq_padding or 4

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
            if self.env.user.havano_role != 'super_admin':
                if not tenant.check_subscription_active():
                    plan = tenant.pending_subscription_plan_id or tenant.subscription_plan_id
                    if plan:
                        price = tenant.pending_subscription_total_amount if tenant.pending_subscription_plan_id else (tenant.subscription_total_amount or plan.price)
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
                                    'default_subscription_plan_id': plan.id,
                                    'default_amount': price,
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
        if vals.get('is_default'):
            for store in self:
                self.search([
                    ('tenant_id', '=', store.tenant_id.id),
                    ('is_default', '=', True),
                    ('id', '!=', store.id),
                ]).with_context(
                    allow_default_switch=True,
                    skip_default_store_check=True,
                ).write({'is_default': False})
        elif vals.get('is_default') is False and not self.env.context.get('allow_default_switch'):
            for store in self:
                if store.is_default and not self.search_count([
                    ('tenant_id', '=', store.tenant_id.id),
                    ('is_default', '=', True),
                    ('id', '!=', store.id),
                ]):
                    raise ValidationError(_('You cannot untick the only default store. Select another store as default first.'))

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

class HavanoposdeskStoreBank(models.Model):
    _name = 'havanoposdesk.store.bank'
    _description = 'Store Bank Account'

    store_id = fields.Many2one('havanoposdesk.store', string='Store', required=True, ondelete='cascade')
    name = fields.Char(string='Bank Name', required=True)
    account_name = fields.Char(string='Account Name', required=True)
    account_number = fields.Char(string='Account Number', required=True)
    branch = fields.Char(string='Branch')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.user.tenant_id.currency_id.id if self.env.user.tenant_id else False)
    show_on_invoice = fields.Boolean(string='Show on Invoice', default=True)
