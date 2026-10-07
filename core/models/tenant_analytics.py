# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api, _
from datetime import datetime, timedelta, date
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


class HavanoTenantAnalytics(models.Model):
    """
    Read-only analytics report for SaaS tenants.
    Aggregates sales counts, revenue, last sale date, last login, and subscription info
    per tenant using a high-performance PostgreSQL view.
    Also provides get_dashboard_data service for the Tenant Analytics Dashboard.
    """
    _name = 'havanoposdesk.tenant.analytics'
    _description = 'Tenant Analytics Report'
    _auto = False
    _rec_name = 'tenant_name'
    _order = 'total_sales_count desc, total_sales_amount desc, tenant_name asc'

    # ── Identity ──────────────────────────────────────────────────────────────
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', readonly=True)
    tenant_name = fields.Char(string='Tenant Name', readonly=True)

    # ── Subscription ──────────────────────────────────────────────────────────
    subscription_plan_id = fields.Many2one('havanoposdesk.subscription.plan', string='Subscription Plan', readonly=True)
    plan_name = fields.Char(string='Plan Name', readonly=True)
    subscription_state = fields.Selection([
        ('active', 'Active'),
        ('pending', 'Pending Payment'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string='Subscription Status', readonly=True)
    is_trial = fields.Boolean(string='Demo / Trial', readonly=True)
    subscription_end_date = fields.Date(string='Expiry Date', readonly=True)

    # ── Sales KPIs ────────────────────────────────────────────────────────────
    total_sales_count = fields.Integer(string='# Sales', readonly=True)
    total_sales_amount = fields.Float(string='Total Revenue ($)', readonly=True, digits=(16, 2))
    last_sale_date = fields.Date(string='Last Sale Date', readonly=True)

    # ── Users & Activity ──────────────────────────────────────────────────────
    user_count = fields.Integer(string='# Users', readonly=True)
    last_login = fields.Datetime(string='Recent Login', readonly=True)
    last_activity = fields.Datetime(string='Recent Usage', readonly=True)

    # ── Wallet & Currency ─────────────────────────────────────────────────────
    account_balance = fields.Float(string='Wallet Balance ($)', readonly=True, digits=(16, 2))
    currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_default_currency', readonly=True)

    def _compute_default_currency(self):
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        default_cur_id = usd.id if usd else self.env.company.currency_id.id
        for record in self:
            record.currency_id = default_cur_id

    # ─────────────────────────────────────────────────────────────────────────
    def init(self):
        """Create or replace the underlying PostgreSQL view."""
        tools.drop_view_if_exists(self.env.cr, 'havanoposdesk_tenant_analytics')
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW havanoposdesk_tenant_analytics AS (
                SELECT
                    t.id                                        AS id,
                    t.id                                        AS tenant_id,
                    t.name                                      AS tenant_name,
                    t.subscription_plan_id                      AS subscription_plan_id,
                    COALESCE(sp.name, 'No Plan')                AS plan_name,
                    COALESCE(t.subscription_state, 'active')   AS subscription_state,
                    CASE
                        WHEN t.subscription_plan_id IS NULL THEN TRUE
                        WHEN sp.is_trial = TRUE OR COALESCE(sp.price, 0) = 0 OR LOWER(sp.name) LIKE '%demo%' OR LOWER(sp.name) LIKE '%trial%' THEN TRUE
                        WHEN t.is_trial = TRUE THEN TRUE
                        ELSE FALSE
                    END                                         AS is_trial,
                    t.subscription_end_date                     AS subscription_end_date,
                    COALESCE(t.account_balance, 0)              AS account_balance,

                    -- Sales KPIs: includes all sales where not return or quotation, handles NULLs safely
                    COALESCE(s.total_sales_count, 0)            AS total_sales_count,
                    COALESCE(s.total_sales_amount, 0.0)         AS total_sales_amount,
                    s.last_sale_date                            AS last_sale_date,

                    -- Users & Logins
                    COALESCE(u.user_count, 0)                   AS user_count,
                    u.last_login                                AS last_login,

                    -- Recent Usage: most recent of user login or sales creation
                    CASE
                        WHEN u.last_login IS NOT NULL AND s.last_sale_create_date IS NOT NULL
                            THEN GREATEST(u.last_login, s.last_sale_create_date)
                        ELSE COALESCE(u.last_login, s.last_sale_create_date)
                    END                                         AS last_activity

                FROM havanoposdesk_tenant t
                LEFT JOIN havanoposdesk_subscription_plan sp
                    ON sp.id = t.subscription_plan_id

                -- Aggregate sales per tenant
                LEFT JOIN (
                    SELECT
                        tenant_id,
                        COUNT(*)                                            AS total_sales_count,
                        SUM(COALESCE(amount_total_base, amount_total, 0.0)) AS total_sales_amount,
                        MAX(posting_date)                                   AS last_sale_date,
                        MAX(create_date)                                    AS last_sale_create_date
                    FROM havanoposdesk_sale
                    WHERE COALESCE(is_return, FALSE) = FALSE
                      AND COALESCE(is_quotation, FALSE) = FALSE
                      AND COALESCE(state, 'done') != 'cancelled'
                    GROUP BY tenant_id
                ) s ON s.tenant_id = t.id

                -- Aggregate user count and last login from res_users_log
                LEFT JOIN (
                    SELECT
                        u.tenant_id,
                        COUNT(DISTINCT u.id)    AS user_count,
                        MAX(l.create_date)      AS last_login
                    FROM res_users u
                    LEFT JOIN res_users_log l ON l.create_uid = u.id
                    WHERE u.active = TRUE
                      AND u.tenant_id IS NOT NULL
                    GROUP BY u.tenant_id
                ) u ON u.tenant_id = t.id

                WHERE t.active = TRUE
            )
        """)

    # ── Action Methods ────────────────────────────────────────────────────────
    def action_open_tenant(self):
        """Open the tenant form from the analytics list row."""
        self.ensure_one()
        return {
            'name': _('Tenant: %s', self.tenant_name),
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.tenant',
            'res_id': self.tenant_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_sales(self):
        """Drill down into this tenant's sales records."""
        self.ensure_one()
        return {
            'name': _('%s – Sales Invoices', self.tenant_name),
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.sale',
            'view_mode': 'list,form',
            'domain': [
                ('tenant_id', '=', self.tenant_id.id),
                ('is_return', '=', False),
                ('is_quotation', '=', False),
            ],
            'context': {
                'default_tenant_id': self.tenant_id.id,
                'search_default_tenant_id': self.tenant_id.id,
            },
            'target': 'current',
        }

    # ── Dashboard Analytics Service ───────────────────────────────────────────
    @api.model
    def get_dashboard_data(self, tenant_id=False, date_from=False, date_to=False, granularity='weekly'):
        """
        Fetch real, aggregated metrics and timeseries datasets for the
        Tenant Analytics Dashboard across Sales, Purchases, Stock Adjustments,
        and Tenant Activity.
        """
        user = self.env.user
        is_super_admin = user.has_group('base.group_system') or user.id == 1

        # Enforce tenant isolation for non-superadmins
        if not is_super_admin:
            tenant_id = user.tenant_id.id if user.tenant_id else False

        # 1. Fetch available tenants list for dropdown
        tenants_data = []
        if is_super_admin:
            tenants = self.env['havanoposdesk.tenant'].search_read(
                [('active', '=', True)], 
                ['id', 'name'], 
                order='name asc'
            )
            tenants_data = [{'id': t['id'], 'name': t['name']} for t in tenants]
        else:
            if user.tenant_id:
                tenants_data = [{'id': user.tenant_id.id, 'name': user.tenant_id.name}]

        # 2. Date parsing and previous period calculation
        now = fields.Datetime.now()
        today = date.today()

        if not date_from or not date_to:
            # Default to current year (or last 6 months to ensure rich data)
            date_from = f"{today.year}-01-01"
            date_to = today.strftime("%Y-%m-%d")

        try:
            d_start = datetime.strptime(str(date_from)[:10], "%Y-%m-%d").date()
            d_end = datetime.strptime(str(date_to)[:10], "%Y-%m-%d").date()
        except Exception:
            d_start = date(today.year, 1, 1)
            d_end = today
            date_from = d_start.strftime("%Y-%m-%d")
            date_to = d_end.strftime("%Y-%m-%d")

        diff_days = (d_end - d_start).days + 1
        p_start = d_start - timedelta(days=diff_days)
        p_end = d_start - timedelta(days=1)

        start_dt_str = f"{d_start.strftime('%Y-%m-%d')} 00:00:00"
        end_dt_str = f"{d_end.strftime('%Y-%m-%d')} 23:59:59"
        p_start_dt_str = f"{p_start.strftime('%Y-%m-%d')} 00:00:00"
        p_end_dt_str = f"{p_end.strftime('%Y-%m-%d')} 23:59:59"

        # 3. Base Domains
        if tenant_id:
            if isinstance(tenant_id, list):
                tenant_domain = [('tenant_id', 'in', tenant_id)]
            else:
                tenant_domain = [('tenant_id', '=', int(tenant_id))]
        else:
            tenant_domain = []

        sale_domain = tenant_domain + [('date', '>=', start_dt_str), ('date', '<=', end_dt_str)]
        prev_sale_domain = tenant_domain + [('date', '>=', p_start_dt_str), ('date', '<=', p_end_dt_str)]

        purchase_domain = tenant_domain + [('posting_date', '>=', start_dt_str), ('posting_date', '<=', end_dt_str)]
        prev_purchase_domain = tenant_domain + [('posting_date', '>=', p_start_dt_str), ('posting_date', '<=', p_end_dt_str)]

        adj_domain = tenant_domain + [('posting_date', '>=', start_dt_str), ('posting_date', '<=', end_dt_str)]
        prev_adj_domain = tenant_domain + [('posting_date', '>=', p_start_dt_str), ('posting_date', '<=', p_end_dt_str)]

        # 4. Fetch Records
        sales = self.env['havanoposdesk.sale'].search(sale_domain, order='date asc')
        prev_sales = self.env['havanoposdesk.sale'].search(prev_sale_domain)

        purchases = self.env['havanoposdesk.purchase'].search(purchase_domain, order='posting_date asc')
        prev_purchases = self.env['havanoposdesk.purchase'].search(prev_purchase_domain)

        adjustments = self.env['havanoposdesk.stock.adjustment'].search(adj_domain, order='posting_date asc')
        prev_adjustments = self.env['havanoposdesk.stock.adjustment'].search(prev_adj_domain)

        # 5. Compute Overall KPIs
        curr_sales_total = sum((s.amount_total_base or s.amount_total or 0.0) for s in sales)
        prev_sales_total = sum((s.amount_total_base or s.amount_total or 0.0) for s in prev_sales)
        sales_growth = self._calculate_growth(curr_sales_total, prev_sales_total)

        curr_purchases_total = sum((p.amount_total_base or p.amount_total or 0.0) for p in purchases)
        prev_purchases_total = sum((p.amount_total_base or p.amount_total or 0.0) for p in prev_purchases)
        purchases_growth = self._calculate_growth(curr_purchases_total, prev_purchases_total)

        # Stock adjustments stats
        curr_adj_count = len(adjustments)
        curr_adj_valuation = sum(a.total_amount_difference or 0.0 for a in adjustments)
        curr_pos_qty = 0.0
        curr_neg_qty = 0.0

        for adj in adjustments:
            diff = adj.total_qty_difference or 0.0
            if diff > 0:
                curr_pos_qty += diff
            elif diff < 0:
                curr_neg_qty += abs(diff)

        # Activity stats
        total_activities = len(sales) + len(purchases) + len(adjustments)
        prev_total_activities = len(prev_sales) + len(prev_purchases) + len(prev_adjustments)
        activity_growth = self._calculate_growth(total_activities, prev_total_activities)

        kpis = {
            'sales': {
                'total_amount': round(curr_sales_total, 2),
                'transactions_count': len(sales),
                'avg_transaction': round(curr_sales_total / len(sales), 2) if sales else 0.0,
                'growth_pct': sales_growth,
            },
            'purchases': {
                'total_amount': round(curr_purchases_total, 2),
                'transactions_count': len(purchases),
                'growth_pct': purchases_growth,
            },
            'stock_adjustments': {
                'operations_count': curr_adj_count,
                'total_valuation_diff': round(curr_adj_valuation, 2),
                'positive_qty': round(curr_pos_qty, 2),
                'negative_qty': round(curr_neg_qty, 2),
            },
            'activity': {
                'total_events': total_activities,
                'sales_events': len(sales),
                'purchase_events': len(purchases),
                'adjustment_events': len(adjustments),
                'growth_pct': activity_growth,
            }
        }

        # 6. Build Timeline Buckets based on granularity
        buckets = self._generate_timeline_buckets(d_start, d_end, granularity)

        # Buckets data storage
        sales_by_bucket = {b['key']: {'amount': 0.0, 'count': 0} for b in buckets}
        purchases_by_bucket = {b['key']: {'amount': 0.0, 'count': 0} for b in buckets}
        adj_by_bucket = {b['key']: {'count': 0, 'pos_qty': 0.0, 'neg_qty': 0.0, 'valuation': 0.0} for b in buckets}

        # Populate Sales
        for s in sales:
            if s.date:
                dt = fields.Datetime.to_datetime(s.date)
                b_key = self._get_bucket_key(dt, granularity)
                if b_key in sales_by_bucket:
                    sales_by_bucket[b_key]['amount'] += (s.amount_total_base or s.amount_total or 0.0)
                    sales_by_bucket[b_key]['count'] += 1

        # Populate Purchases
        for p in purchases:
            if p.posting_date:
                dt = fields.Datetime.to_datetime(p.posting_date)
                b_key = self._get_bucket_key(dt, granularity)
                if b_key in purchases_by_bucket:
                    purchases_by_bucket[b_key]['amount'] += (p.amount_total_base or p.amount_total or 0.0)
                    purchases_by_bucket[b_key]['count'] += 1

        # Populate Adjustments
        for a in adjustments:
            if a.posting_date:
                dt = fields.Datetime.to_datetime(a.posting_date)
                b_key = self._get_bucket_key(dt, granularity)
                if b_key in adj_by_bucket:
                    adj_by_bucket[b_key]['count'] += 1
                    adj_by_bucket[b_key]['valuation'] += (a.total_amount_difference or 0.0)
                    d_qty = a.total_qty_difference or 0.0
                    if d_qty > 0:
                        adj_by_bucket[b_key]['pos_qty'] += d_qty
                    elif d_qty < 0:
                        adj_by_bucket[b_key]['neg_qty'] += abs(d_qty)

        # Extract aligned chart datasets
        labels = [b['label'] for b in buckets]

        sales_chart = {
            'labels': labels,
            'amounts': [round(sales_by_bucket[b['key']]['amount'], 2) for b in buckets],
            'counts': [sales_by_bucket[b['key']]['count'] for b in buckets],
        }

        purchase_chart = {
            'labels': labels,
            'amounts': [round(purchases_by_bucket[b['key']]['amount'], 2) for b in buckets],
            'counts': [purchases_by_bucket[b['key']]['count'] for b in buckets],
        }

        stock_chart = {
            'labels': labels,
            'pos_qty': [round(adj_by_bucket[b['key']]['pos_qty'], 2) for b in buckets],
            'neg_qty': [round(adj_by_bucket[b['key']]['neg_qty'], 2) for b in buckets],
            'valuation': [round(adj_by_bucket[b['key']]['valuation'], 2) for b in buckets],
            'operations': [adj_by_bucket[b['key']]['count'] for b in buckets],
        }

        activity_chart = {
            'labels': labels,
            'sales_events': [sales_by_bucket[b['key']]['count'] for b in buckets],
            'purchase_events': [purchases_by_bucket[b['key']]['count'] for b in buckets],
            'adjustment_events': [adj_by_bucket[b['key']]['count'] for b in buckets],
            'total_events': [sales_by_bucket[b['key']]['count'] + purchases_by_bucket[b['key']]['count'] + adj_by_bucket[b['key']]['count'] for b in buckets],
        }

        total_sales_count = len(sales)
        total_purchases_count = len(purchases)
        total_adj_count = len(adjustments)

        distribution_chart = {
            'labels': ['Sales Invoices', 'Purchase Orders', 'Stock Adjustments'],
            'data': [total_sales_count, total_purchases_count, total_adj_count],
            'colors': ['#0080ff', '#38bdf8', '#94a3b8'],
        }

        breakdown_chart = {
            'labels': ['Positive Adj (Stock In)', 'Negative Adj (Stock Out)', 'Purchase Orders', 'Sales Invoices'],
            'data': [
                len(adjustments.filtered(lambda a: (a.total_qty_difference or 0) > 0)),
                len(adjustments.filtered(lambda a: (a.total_qty_difference or 0) < 0)),
                total_purchases_count,
                total_sales_count,
            ],
            'colors': ['#0080ff', '#38bdf8', '#64748b', '#cbd5e1'],
        }

        return {
            'tenants': tenants_data,
            'selected_tenant_id': int(tenant_id) if tenant_id else False,
            'date_from': date_from,
            'date_to': date_to,
            'granularity': granularity,
            'kpis': kpis,
            'sales_chart': sales_chart,
            'purchase_chart': purchase_chart,
            'stock_chart': stock_chart,
            'activity_chart': activity_chart,
            'distribution_chart': distribution_chart,
            'breakdown_chart': breakdown_chart,
        }

    def _calculate_growth(self, current, previous):
        if not previous or previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100.0, 1)

    def _get_bucket_key(self, dt, granularity):
        if granularity == 'daily':
            return dt.strftime('%Y-%m-%d')
        elif granularity == 'monthly':
            return dt.strftime('%Y-%m')
        else:  # 'weekly'
            year, week, _ = dt.isocalendar()
            return f"{year}-W{week:02d}"

    def _generate_timeline_buckets(self, start_date, end_date, granularity):
        buckets = []
        curr = start_date

        if granularity == 'daily':
            while curr <= end_date:
                key = curr.strftime('%Y-%m-%d')
                label = curr.strftime('%a, %b %d')
                buckets.append({'key': key, 'label': label})
                curr += timedelta(days=1)
        elif granularity == 'monthly':
            # Iterate month by month
            y, m = curr.year, curr.month
            end_y, end_m = end_date.year, end_date.month
            while (y < end_y) or (y == end_y and m <= end_m):
                key = f"{y:04d}-{m:02d}"
                d_obj = date(y, m, 1)
                label = d_obj.strftime('%b %Y')
                buckets.append({'key': key, 'label': label})
                m += 1
                if m > 12:
                    m = 1
                    y += 1
        else:  # 'weekly'
            # Start on Monday of the start_date's week
            curr_monday = curr - timedelta(days=curr.weekday())
            seen_weeks = set()
            while curr_monday <= end_date:
                year, week, _ = curr_monday.isocalendar()
                key = f"{year}-W{week:02d}"
                if key not in seen_weeks:
                    seen_weeks.add(key)
                    label = curr_monday.strftime('%b %d')
                    buckets.append({'key': key, 'label': label})
                curr_monday += timedelta(days=7)

        # Ensure at least 1 bucket exists
        if not buckets:
            buckets.append({'key': 'all', 'label': 'Current Period'})

        return buckets
