# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime, timedelta, date
from collections import defaultdict
import math

class HavanoposdeskTenantAnalytics(models.AbstractModel):
    _name = 'havanoposdesk.tenant.analytics'
    _description = 'Tenant Analytics Dashboard Service'

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
