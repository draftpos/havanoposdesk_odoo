import base64
import io
import json
import logging
from datetime import datetime, date
import openpyxl
import csv

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PurchaseImportWizard(models.TransientModel):
    _name = 'havanoposdesk.purchase.import.wizard'
    _description = 'Purchase Invoices Smart Importer & Verifier'

    file = fields.Binary(string='Upload Excel or CSV File', required=True)
    filename = fields.Char(string='Filename')

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant',
        string='Tenant',
        default=lambda self: self.env.user.tenant_id or self.env['havanoposdesk.tenant'].search([], limit=1),
        required=True,
        help="Target tenant. If tenant is missing in file rows, this tenant will be used."
    )
    store_id = fields.Many2one(
        'havanoposdesk.store',
        string='Default Store',
        domain="[('tenant_id', '=', tenant_id)]",
        help="Default receiving store when not specified per row."
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Default Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )
    payment_status = fields.Selection([
        ('cash', 'Paid (Cash)'),
        ('account', 'On Account (Credit)'),
    ], string='Default Payment Status', default='cash', required=True)

    account_id = fields.Many2one(
        'havanoposdesk.account',
        string='Cash/Bank Payment Account',
        domain="[('tenant_id', '=', tenant_id), ('type', 'in', ['Cash', 'Bank'])]",
        help="Account for cash purchases."
    )

    auto_create_supplier = fields.Boolean(
        string='Auto-create Missing Suppliers',
        default=True,
        help="If checked, any supplier in the file not yet in the system will be created automatically."
    )
    auto_create_product = fields.Boolean(
        string='Auto-create Missing Products',
        default=True,
        help="If checked, any item in the file not yet in the catalog will be created automatically."
    )

    # State & verification flags
    state = fields.Selection([
        ('draft', 'Upload & Test'),
        ('tested', 'Verification Passed'),
        ('imported', 'Imported'),
    ], default='draft')
    is_tested = fields.Boolean(string='Tested', default=False)
    has_errors = fields.Boolean(string='Has Errors', default=False)

    # Summary Metrics
    purchases_count = fields.Integer(string='Purchases Detected', default=0)
    lines_count = fields.Integer(string='Line Items Detected', default=0)
    total_amount = fields.Float(string='Total Value ($)', default=0.0)

    test_summary_html = fields.Html(string='Verification Report', readonly=True)
    parsed_data_json = fields.Text(string='Parsed Data Cache')

    @api.onchange('tenant_id')
    def _onchange_tenant_id(self):
        if self.tenant_id:
            store = self.env['havanoposdesk.store'].search([('tenant_id', '=', self.tenant_id.id)], limit=1)
            if store:
                self.store_id = store.id
            if self.tenant_id.currency_id:
                self.currency_id = self.tenant_id.currency_id.id

    def _clean_str(self, val):
        if val is None:
            return ''
        s = str(val).strip()
        return '' if s.lower() in ('none', 'nan', 'null') else s

    def _parse_date(self, val):
        if not val:
            return fields.Datetime.now()
        if isinstance(val, datetime):
            return val
        if isinstance(val, date):
            return datetime.combine(val, datetime.min.time())

        s = str(val).strip()
        for fmt in (
            '%d-%m-%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S',
            '%d-%m-%Y', '%Y-%m-%d',
            '%d/%m/%Y %H:%M:%S', '%Y/%m/%d %H:%M:%S',
            '%d/%m/%Y', '%Y/%m/%d',
            '%m/%d/%Y', '%d.%m.%Y'
        ):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                pass
        return fields.Datetime.now()

    def _read_file_rows(self):
        if not self.file:
            raise UserError(_("Please upload an Excel or CSV file first."))

        file_bytes = base64.b64decode(self.file)
        rows_data = []

        is_excel = False
        if self.filename and (self.filename.lower().endswith('.xlsx') or self.filename.lower().endswith('.xls')):
            is_excel = True
        elif file_bytes[:4] == b'PK\x03\x04':
            is_excel = True

        if is_excel:
            in_mem = io.BytesIO(file_bytes)
            wb = openpyxl.load_workbook(in_mem, data_only=True)
            sheet = wb.active
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                raise UserError(_("The uploaded Excel sheet contains no data."))
            header_row = [self._clean_str(c).lower() for c in rows[0]]
            for r in rows[1:]:
                row_dict = {}
                for idx, h in enumerate(header_row):
                    if idx < len(r):
                        row_dict[h] = r[idx]
                rows_data.append(row_dict)
        else:
            try:
                text_content = file_bytes.decode('utf-8-sig')
            except Exception:
                text_content = file_bytes.decode('latin-1')

            sample = text_content[:2048]
            delimiter = ','
            if ';' in sample and sample.count(';') > sample.count(','):
                delimiter = ';'
            elif '\t' in sample and sample.count('\t') > sample.count(','):
                delimiter = '\t'

            reader = csv.reader(io.StringIO(text_content), delimiter=delimiter)
            rows = list(reader)
            if not rows:
                raise UserError(_("The uploaded CSV file contains no data."))
            header_row = [self._clean_str(c).lower() for c in rows[0]]
            for r in rows[1:]:
                row_dict = {}
                for idx, h in enumerate(header_row):
                    if idx < len(r):
                        row_dict[h] = r[idx]
                rows_data.append(row_dict)

        return rows_data

    def _detect_column_keys(self, row_dict):
        col_map = {}
        for k in row_dict.keys():
            lk = k.lower().replace('_', ' ').replace('-', ' ').strip()
            if 'external' in lk or 'reference' in lk or 'bill' in lk or 'invoice' in lk:
                col_map.setdefault('ref', k)
            elif lk == 'id':
                col_map.setdefault('id', k)
            elif 'date' in lk or 'posting' in lk:
                col_map['date'] = k
            elif 'supplier' in lk or 'vendor' in lk:
                col_map['supplier'] = k
            elif 'item' in lk or 'product' in lk or 'description' in lk:
                col_map.setdefault('item', k)
            elif 'uom' in lk or 'unit' in lk:
                col_map['uom'] = k
            elif 'price' in lk or 'cost' in lk or 'rate' in lk:
                col_map['rate'] = k
            elif 'qty' in lk or 'quantity' in lk:
                col_map['qty'] = k
            elif 'store' in lk or 'branch' in lk or 'warehouse' in lk:
                col_map['store'] = k
            elif 'tenant' in lk:
                col_map['tenant'] = k
            elif 'payment status' in lk:
                col_map['payment_status'] = k
            elif 'payment account' in lk:
                col_map['payment_account'] = k
            elif 'total' in lk or 'amount' in lk:
                col_map.setdefault('total', k)

        # Fallback for reference if not mapped from external/reference/bill
        if 'ref' not in col_map and 'id' in col_map:
            col_map['ref'] = col_map['id']

        return col_map

    def action_test_file(self):
        self.ensure_one()
        rows_data = self._read_file_rows()
        if not rows_data:
            raise UserError(_("No rows found in uploaded file."))

        col_map = self._detect_column_keys(rows_data[0])
        if 'item' not in col_map:
            raise UserError(_("Could not find an 'Item' or 'Product' column in the uploaded file."))

        target_tenant = self.tenant_id or self.env.user.tenant_id
        if not target_tenant:
            target_tenant = self.env['havanoposdesk.tenant'].search([], limit=1)

        existing_products = {
            p.name.strip().lower(): p.id
            for p in self.env['havanoposdesk.product'].search([('tenant_id', '=', target_tenant.id)])
        }
        existing_suppliers = {
            s.name.strip().lower(): s.id
            for s in self.env['havanoposdesk.supplier'].search([('tenant_id', '=', target_tenant.id)])
        }
        existing_stores = {
            s.name.strip().lower(): s.id
            for s in self.env['havanoposdesk.store'].search([('tenant_id', '=', target_tenant.id)])
        }
        default_store_id = self.store_id.id if self.store_id else (
            next(iter(existing_stores.values())) if existing_stores else False
        )

        purchases = []
        current_purch = None
        new_items = set()
        new_suppliers = set()
        validation_errors = []

        total_value = 0.0
        total_lines = 0

        for row_idx, r in enumerate(rows_data, start=2):
            raw_ref = self._clean_str(r.get(col_map.get('ref', ''))) if 'ref' in col_map else ''
            if not raw_ref and 'id' in col_map:
                raw_ref = self._clean_str(r.get(col_map.get('id', '')))
            raw_ref = raw_ref.strip(' "\'')

            raw_item = self._clean_str(r.get(col_map.get('item', ''))) if 'item' in col_map else ''
            raw_qty = self._clean_str(r.get(col_map.get('qty', ''))) if 'qty' in col_map else '1.0'
            raw_rate = self._clean_str(r.get(col_map.get('rate', ''))) if 'rate' in col_map else '0.0'
            raw_supp = self._clean_str(r.get(col_map.get('supplier', ''))) if 'supplier' in col_map else ''
            raw_date = r.get(col_map.get('date', '')) if 'date' in col_map else None
            raw_store = self._clean_str(r.get(col_map.get('store', ''))) if 'store' in col_map else ''
            raw_uom = self._clean_str(r.get(col_map.get('uom', ''))) if 'uom' in col_map else ''
            raw_pay_status = self._clean_str(r.get(col_map.get('payment_status', ''))) if 'payment_status' in col_map else ''

            if not raw_ref and not raw_item:
                continue

            row_pay_status = self.payment_status
            if raw_pay_status:
                rps = raw_pay_status.lower()
                if 'paid' in rps or 'cash' in rps or 'bank' in rps:
                    row_pay_status = 'cash'
                elif 'account' in rps or 'credit' in rps or 'unpaid' in rps:
                    row_pay_status = 'account'

            if raw_ref and (not current_purch or current_purch['ref'] != raw_ref):
                dt_obj = self._parse_date(raw_date)
                supp_name = raw_supp or 'Default Supplier'
                store_key = raw_store.strip().lower()
                matched_store_id = existing_stores.get(store_key, default_store_id)

                if supp_name.lower() not in existing_suppliers:
                    new_suppliers.add(supp_name)

                current_purch = {
                    'ref': raw_ref,
                    'date': dt_obj.strftime('%Y-%m-%d %H:%M:%S'),
                    'supplier_name': supp_name,
                    'store_id': matched_store_id,
                    'store_name': raw_store or (self.store_id.name if self.store_id else 'Default Store'),
                    'payment_status': row_pay_status,
                    'lines': [],
                    'first_row': row_idx
                }
                purchases.append(current_purch)
            elif not current_purch:
                synth_ref = f"BILL-{str(len(purchases)+1).zfill(5)}"
                dt_obj = self._parse_date(raw_date)
                supp_name = raw_supp or 'Default Supplier'
                store_key = raw_store.strip().lower()
                matched_store_id = existing_stores.get(store_key, default_store_id)

                if supp_name.lower() not in existing_suppliers:
                    new_suppliers.add(supp_name)

                current_purch = {
                    'ref': synth_ref,
                    'date': dt_obj.strftime('%Y-%m-%d %H:%M:%S'),
                    'supplier_name': supp_name,
                    'store_id': matched_store_id,
                    'store_name': raw_store or (self.store_id.name if self.store_id else 'Default Store'),
                    'payment_status': row_pay_status,
                    'lines': [],
                    'first_row': row_idx
                }
                purchases.append(current_purch)

            if raw_item:
                try:
                    qty = float(raw_qty.replace(',', '') if raw_qty else 1.0)
                except ValueError:
                    validation_errors.append(f"Row {row_idx}: Invalid quantity '{raw_qty}' for item '{raw_item}'.")
                    qty = 1.0

                try:
                    rate = float(raw_rate.replace(',', '') if raw_rate else 0.0)
                except ValueError:
                    validation_errors.append(f"Row {row_idx}: Invalid cost rate '{raw_rate}' for item '{raw_item}'.")
                    rate = 0.0

                if raw_item.strip().lower() not in existing_products:
                    new_items.add(raw_item.strip())

                subtotal = qty * rate
                total_value += subtotal
                total_lines += 1

                current_purch['lines'].append({
                    'item': raw_item.strip(),
                    'uom': raw_uom,
                    'qty': qty,
                    'rate': rate,
                    'subtotal': subtotal,
                    'row': row_idx
                })

        has_err = len(validation_errors) > 0
        self.purchases_count = len(purchases)
        self.lines_count = total_lines
        self.total_amount = total_value
        self.has_errors = has_err
        self.is_tested = True
        self.state = 'draft' if has_err else 'tested'

        self.parsed_data_json = json.dumps(purchases)

        # Build Compact HTML Verification Report
        report_parts = []
        if not has_err:
            report_parts.append("""
                <div class="alert alert-success d-flex align-items-center py-2 px-3 mb-2" style="border-radius: 6px; border-left: 4px solid #28a745;">
                    <i class="fa fa-check-circle text-success me-2 fs-5"></i>
                    <div>
                        <div class="fw-bold text-success">Verification Passed Successfully</div>
                        <div class="text-muted small">All purchase bills and line items validated. Ready for import.</div>
                    </div>
                </div>
            """)
        else:
            report_parts.append(f"""
                <div class="alert alert-danger d-flex align-items-center py-2 px-3 mb-2" style="border-radius: 6px; border-left: 4px solid #dc3545;">
                    <i class="fa fa-exclamation-triangle text-danger me-2 fs-5"></i>
                    <div>
                        <div class="fw-bold text-danger">Found {len(validation_errors)} Validation Errors</div>
                        <div class="text-muted small">Please correct the data rows below before proceeding with the import.</div>
                    </div>
                </div>
            """)

        # Metric Badges - Compact
        report_parts.append(f"""
            <div class="row g-2 mb-2 text-center">
                <div class="col-sm-3">
                    <div class="p-1 border rounded bg-white">
                        <div class="text-muted small" style="font-size: 0.72rem; letter-spacing: 0.5px;">PURCHASES</div>
                        <div class="fw-bold text-primary fs-5">{self.purchases_count:,}</div>
                    </div>
                </div>
                <div class="col-sm-3">
                    <div class="p-1 border rounded bg-white">
                        <div class="text-muted small" style="font-size: 0.72rem; letter-spacing: 0.5px;">LINE ITEMS</div>
                        <div class="fw-bold text-info fs-5">{self.lines_count:,}</div>
                    </div>
                </div>
                <div class="col-sm-3">
                    <div class="p-1 border rounded bg-white">
                        <div class="text-muted small" style="font-size: 0.72rem; letter-spacing: 0.5px;">TOTAL VALUE</div>
                        <div class="fw-bold text-success fs-5">${self.total_amount:,.2f}</div>
                    </div>
                </div>
                <div class="col-sm-3">
                    <div class="p-1 border rounded bg-white">
                        <div class="text-muted small" style="font-size: 0.72rem; letter-spacing: 0.5px;">TENANT</div>
                        <div class="fw-bold text-dark text-truncate pt-1" title="{target_tenant.name}">{target_tenant.name}</div>
                    </div>
                </div>
            </div>
        """)

        # Detailed Entity Reconciliation Card - Compact
        supp_auto_badge = '<span class="badge bg-success ms-1" style="font-size: 0.7rem;">Auto-create Enabled</span>' if self.auto_create_supplier else '<span class="badge bg-warning ms-1" style="font-size: 0.7rem;">Existing Only</span>'
        prod_auto_badge = '<span class="badge bg-success ms-1" style="font-size: 0.7rem;">Auto-create Enabled</span>' if self.auto_create_product else '<span class="badge bg-warning ms-1" style="font-size: 0.7rem;">Existing Only</span>'

        report_parts.append(f"""
            <div class="card border mb-2">
                <div class="card-header bg-light py-1 px-2 fw-bold text-dark small">
                    <i class="fa fa-database me-1"></i> Supplier &amp; Catalog Matching
                </div>
                <div class="card-body py-1 px-2 small">
                    <div class="row">
                        <div class="col-md-6">
                            <div class="d-flex justify-content-between align-items-center">
                                <span><strong>Products:</strong> {len(existing_products)} Matched, <strong class="text-primary">{len(new_items)} New</strong></span>
                                <span>{prod_auto_badge}</span>
                            </div>
                            {"<div class='text-muted' style='font-size: 0.75rem;'>Sample new: " + ", ".join(list(new_items)[:3]) + "...</div>" if new_items else "<div class='text-success' style='font-size: 0.75rem;'>All items matched in catalog!</div>"}
                        </div>
                        <div class="col-md-6">
                            <div class="d-flex justify-content-between align-items-center">
                                <span><strong>Suppliers:</strong> {len(existing_suppliers)} Matched, <strong class="text-primary">{len(new_suppliers)} New</strong></span>
                                <span>{supp_auto_badge}</span>
                            </div>
                            {"<div class='text-muted' style='font-size: 0.75rem;'>Sample new: " + ", ".join(list(new_suppliers)[:3]) + "...</div>" if new_suppliers else "<div class='text-success' style='font-size: 0.75rem;'>All suppliers matched!</div>"}
                        </div>
                    </div>
                </div>
            </div>
        """)

        # Error Details - Compact
        if validation_errors:
            error_list_html = "".join([f"<li class='text-danger py-0'>{err}</li>" for err in validation_errors[:10]])
            if len(validation_errors) > 10:
                error_list_html += f"<li class='text-muted py-0'>... and {len(validation_errors)-10} more errors.</li>"
            report_parts.append(f"""
                <div class="card border-danger mb-2">
                    <div class="card-header bg-danger text-white py-1 px-2 fw-bold small">
                        <i class="fa fa-times-circle me-1"></i> Errors to Fix in Spreadsheet
                    </div>
                    <div class="card-body py-1 px-2 small">
                        <ul class="mb-0 ps-3">{error_list_html}</ul>
                    </div>
                </div>
            """)

        self.test_summary_html = "".join(report_parts)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_proceed_import(self):
        self.ensure_one()
        if not self.is_tested or self.has_errors:
            raise UserError(_("You must run 'Test & Verify Data' before importing."))

        if not self.parsed_data_json:
            raise UserError(_("No verified data cache found."))

        purchases_data = json.loads(self.parsed_data_json)
        if not purchases_data:
            raise UserError(_("No purchases to import."))

        target_tenant = self.tenant_id or self.env.user.tenant_id
        if not target_tenant:
            target_tenant = self.env['havanoposdesk.tenant'].search([], limit=1)

        # 1. Ensure stores exist
        Store = self.env['havanoposdesk.store'].sudo()
        default_store = self.store_id or Store.search([('tenant_id', '=', target_tenant.id)], limit=1)
        if not default_store:
            default_store = Store.create({'name': 'Default Store', 'tenant_id': target_tenant.id})
        fallback_store_id = default_store.id

        store_cache = {
            s.name.strip().lower(): s.id
            for s in Store.search([('tenant_id', '=', target_tenant.id)])
        }
        for purch in purchases_data:
            sname = (purch.get('store_name') or '').strip()
            if sname and sname.lower() not in store_cache:
                new_st = Store.create({'name': sname, 'tenant_id': target_tenant.id})
                store_cache[sname.lower()] = new_st.id

        # 2. Ensure suppliers exist
        Supplier = self.env['havanoposdesk.supplier'].sudo()
        supp_cache = {
            s.name.strip().lower(): s.id
            for s in Supplier.search([('tenant_id', '=', target_tenant.id)])
        }
        for purch in purchases_data:
            sname = (purch.get('supplier_name') or 'Default Supplier').strip()
            skey = sname.lower()
            if skey not in supp_cache:
                if self.auto_create_supplier:
                    st_id = store_cache.get((purch.get('store_name') or '').strip().lower(), fallback_store_id)
                    new_s = Supplier.create({
                        'name': sname,
                        'tenant_id': target_tenant.id,
                        'store_id': st_id
                    })
                    supp_cache[skey] = new_s.id
                else:
                    first_s = Supplier.search([('tenant_id', '=', target_tenant.id)], limit=1)
                    supp_cache[skey] = first_s.id if first_s else False

        # 3. Ensure products exist
        Product = self.env['havanoposdesk.product'].sudo()
        prod_cache = {
            p.name.strip().lower(): p.id
            for p in Product.search([('tenant_id', '=', target_tenant.id)])
        }
        for purch in purchases_data:
            st_id = store_cache.get((purch.get('store_name') or '').strip().lower(), fallback_store_id)
            for l in purch.get('lines', []):
                pname = (l.get('item') or '').strip()
                pkey = pname.lower()
                if pkey and pkey not in prod_cache:
                    if self.auto_create_product:
                        new_p = Product.create({
                            'name': pname,
                            'tenant_id': target_tenant.id,
                            'buying_price': l.get('rate', 0.0),
                            'store_ids': [(4, st_id)] if st_id else False
                        })
                        prod_cache[pkey] = new_p.id
                    else:
                        first_p = Product.search([('tenant_id', '=', target_tenant.id)], limit=1)
                        prod_cache[pkey] = first_p.id if first_p else False

        # 4. Ensure cash/bank account exists
        Account = self.env['havanoposdesk.account'].sudo()
        cash_account_id = self.account_id.id if self.account_id else False
        if not cash_account_id:
            acc = Account.search([
                ('tenant_id', '=', target_tenant.id),
                ('type', 'in', ['Cash', 'Bank']),
                ('is_on_account', '=', False)
            ], limit=1)
            if acc:
                cash_account_id = acc.id
            else:
                new_acc = Account.create({
                    'name': 'Cash',
                    'type': 'Cash',
                    'tenant_id': target_tenant.id,
                })
                cash_account_id = new_acc.id

        currency_id_val = self.currency_id.id if self.currency_id else (
            target_tenant.currency_id.id if target_tenant.currency_id else self.env.company.currency_id.id
        )

        PurchaseOrder = self.env['havanoposdesk.purchase'].sudo()
        created_ids = []
        batch_size = 300
        current_batch_vals = []

        for purch in purchases_data:
            supp_id = supp_cache.get((purch.get('supplier_name') or '').strip().lower(), False)
            store_id_val = store_cache.get((purch.get('store_name') or '').strip().lower(), fallback_store_id)
            purch_pay_status = purch.get('payment_status', self.payment_status)

            lines_vals = []
            for l in purch.get('lines', []):
                pid = prod_cache.get((l.get('item') or '').strip().lower(), False)
                if not pid:
                    continue
                lines_vals.append((0, 0, {
                    'product_id': pid,
                    'name': l.get('item', 'Item'),
                    'accepted_qty': l.get('qty', 1.0),
                    'rate': l.get('rate', 0.0),
                    'tenant_id': target_tenant.id,
                }))

            if not lines_vals:
                continue

            purch_vals = {
                'name': 'New',
                'external_ref': purch.get('ref'),
                'tenant_id': target_tenant.id,
                'store_id': store_id_val,
                'supplier': supp_id,
                'posting_date': purch.get('date'),
                'currency_id': currency_id_val,
                'payment_status': purch_pay_status,
                'account_id': cash_account_id if purch_pay_status == 'cash' else False,
                'state': 'posted',
                'line_ids': lines_vals,
            }
            current_batch_vals.append(purch_vals)

            if len(current_batch_vals) >= batch_size:
                records = PurchaseOrder.create(current_batch_vals)
                created_ids.extend(records.ids)
                current_batch_vals = []
                self.env.cr.commit()

        if current_batch_vals:
            records = PurchaseOrder.create(current_batch_vals)
            created_ids.extend(records.ids)
            self.env.cr.commit()

        self.state = 'imported'

        return {
            'name': _('Imported Purchases'),
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.purchase',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_ids)],
            'target': 'current',
        }
