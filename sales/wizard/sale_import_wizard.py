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


class SaleImportWizard(models.TransientModel):
    _name = 'havanoposdesk.sale.import.wizard'
    _description = 'Sales Invoices Smart Importer & Verifier'

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
        string='Default / Fallback Store',
        domain="[('tenant_id', '=', tenant_id)]",
        help="Used when the file row does not specify a store or the store is not found."
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
        help="Account credited for cash sales. If empty, the system automatically uses the tenant default cash account."
    )

    auto_create_customer = fields.Boolean(
        string='Auto-create Missing Customers',
        default=True,
        help="If checked, any customer in the file that does not yet exist in this tenant will be created automatically."
    )
    auto_create_product = fields.Boolean(
        string='Auto-create Missing Products',
        default=True,
        help="If checked, any item in the file that does not yet exist in this tenant will be created automatically."
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
    invoices_count = fields.Integer(string='Invoices Detected', default=0)
    lines_count = fields.Integer(string='Line Items Detected', default=0)
    total_amount = fields.Float(string='Total Value ($)', default=0.0)
    matched_customers_count = fields.Integer(string='Matched Customers', default=0)
    new_customers_count = fields.Integer(string='New Customers', default=0)
    matched_products_count = fields.Integer(string='Matched Products', default=0)
    new_products_count = fields.Integer(string='New Products', default=0)

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
        """Parse various date formats into an Odoo datetime string."""
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
                dt = datetime.strptime(s, fmt)
                return dt
            except ValueError:
                pass
        return fields.Datetime.now()

    def _read_file_rows(self):
        """Reads Excel or CSV file into list of row dictionaries."""
        if not self.file:
            raise UserError(_("Please upload an Excel (.xlsx) or CSV file first."))

        file_bytes = base64.b64decode(self.file)
        rows_data = []

        is_excel = False
        if self.filename and (self.filename.lower().endswith('.xlsx') or self.filename.lower().endswith('.xls')):
            is_excel = True
        else:
            # Check magic bytes for zip (xlsx is a zip file)
            if file_bytes[:4] == b'PK\x03\x04':
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

            # Detect delimiter
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
        """Map flexible user headers to standardized internal keys."""
        col_map = {}
        for k in row_dict.keys():
            lk = k.lower().replace('_', ' ').replace('-', ' ').strip()
            if 'local' in lk and 'id' in lk:
                col_map['local_id'] = k
            elif 'invoice' in lk and ('no' in lk or 'id' in lk or 'num' in lk):
                col_map.setdefault('local_id', k)
            elif lk in ('id', 'ticket no', 'receipt no'):
                col_map.setdefault('local_id', k)
            elif 'date' in lk:
                col_map['date'] = k
            elif 'customer' in lk or 'client' in lk:
                col_map['customer'] = k
            elif 'item' in lk or 'product' in lk or 'description' in lk:
                col_map.setdefault('item', k)
            elif 'uom' in lk or 'unit' in lk:
                col_map['uom'] = k
            elif 'price' in lk or 'rate' in lk:
                col_map['price'] = k
            elif 'qty' in lk or 'quantity' in lk:
                col_map['qty'] = k
            elif 'store' in lk or 'branch' in lk:
                col_map['store'] = k
            elif 'tenant' in lk:
                col_map['tenant'] = k
            elif 'total' in lk or 'amount' in lk:
                col_map.setdefault('total', k)
            elif 'pricelist' in lk:
                col_map['pricelist'] = k
        return col_map

    def action_test_file(self):
        """Test and verify uploaded data without writing to database."""
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

        # Pre-cache DB records for fast validation
        existing_products = {
            p.name.strip().lower(): p.id
            for p in self.env['havanoposdesk.product'].search([('tenant_id', '=', target_tenant.id)])
        }
        existing_customers = {
            c.name.strip().lower(): c.id
            for c in self.env['havanoposdesk.customer'].search([('tenant_id', '=', target_tenant.id)])
        }
        existing_stores = {
            s.name.strip().lower(): s.id
            for s in self.env['havanoposdesk.store'].search([('tenant_id', '=', target_tenant.id)])
        }
        default_store_id = self.store_id.id if self.store_id else (
            next(iter(existing_stores.values())) if existing_stores else False
        )

        invoices = []
        current_inv = None
        new_items = set()
        new_customers = set()
        validation_warnings = []
        validation_errors = []

        total_value = 0.0
        total_lines = 0

        for row_idx, r in enumerate(rows_data, start=2):
            raw_loc_id = self._clean_str(r.get(col_map.get('local_id', ''))) if 'local_id' in col_map else ''
            raw_item = self._clean_str(r.get(col_map.get('item', ''))) if 'item' in col_map else ''
            raw_qty = self._clean_str(r.get(col_map.get('qty', ''))) if 'qty' in col_map else '1.0'
            raw_price = self._clean_str(r.get(col_map.get('price', ''))) if 'price' in col_map else '0.0'
            raw_cust = self._clean_str(r.get(col_map.get('customer', ''))) if 'customer' in col_map else ''
            raw_date = r.get(col_map.get('date', '')) if 'date' in col_map else None
            raw_store = self._clean_str(r.get(col_map.get('store', ''))) if 'store' in col_map else ''
            raw_uom = self._clean_str(r.get(col_map.get('uom', ''))) if 'uom' in col_map else ''

            if not raw_loc_id and not raw_item:
                continue

            # Start a new invoice header
            if raw_loc_id and (not current_inv or current_inv['local_id'] != raw_loc_id):
                dt_obj = self._parse_date(raw_date)
                cust_name = raw_cust or 'Walk-in Customer'
                store_key = raw_store.strip().lower()
                matched_store_id = existing_stores.get(store_key, default_store_id)

                if cust_name.lower() not in existing_customers:
                    new_customers.add(cust_name)

                current_inv = {
                    'local_id': raw_loc_id,
                    'date': dt_obj.strftime('%Y-%m-%d %H:%M:%S'),
                    'customer_name': cust_name,
                    'store_id': matched_store_id,
                    'store_name': raw_store or (self.store_id.name if self.store_id else 'Default Store'),
                    'lines': [],
                    'first_row': row_idx
                }
                invoices.append(current_inv)
            elif not current_inv:
                # First row didn't have local_id; assign synthetic ID
                synth_id = f"IMP-{str(len(invoices)+1).zfill(5)}"
                dt_obj = self._parse_date(raw_date)
                cust_name = raw_cust or 'Walk-in Customer'
                matched_store_id = existing_stores.get(raw_store.strip().lower(), default_store_id)

                if cust_name.lower() not in existing_customers:
                    new_customers.add(cust_name)

                current_inv = {
                    'local_id': synth_id,
                    'date': dt_obj.strftime('%Y-%m-%d %H:%M:%S'),
                    'customer_name': cust_name,
                    'store_id': matched_store_id,
                    'store_name': raw_store or (self.store_id.name if self.store_id else 'Default Store'),
                    'lines': [],
                    'first_row': row_idx
                }
                invoices.append(current_inv)

            # Process line item
            if raw_item:
                try:
                    qty = float(raw_qty.replace(',', '') if raw_qty else 1.0)
                except ValueError:
                    validation_errors.append(f"Row {row_idx}: Invalid quantity '{raw_qty}' for item '{raw_item}'.")
                    qty = 1.0

                try:
                    price = float(raw_price.replace(',', '') if raw_price else 0.0)
                except ValueError:
                    validation_errors.append(f"Row {row_idx}: Invalid price '{raw_price}' for item '{raw_item}'.")
                    price = 0.0

                item_key = raw_item.strip().lower()
                if item_key not in existing_products:
                    new_items.add(raw_item.strip())

                subtotal = qty * price
                total_value += subtotal
                total_lines += 1

                current_inv['lines'].append({
                    'item': raw_item.strip(),
                    'uom': raw_uom,
                    'qty': qty,
                    'price': price,
                    'subtotal': subtotal,
                    'row': row_idx
                })

        has_err = len(validation_errors) > 0
        self.invoices_count = len(invoices)
        self.lines_count = total_lines
        self.total_amount = total_value
        self.new_customers_count = len(new_customers)
        self.matched_customers_count = max(0, len(existing_customers) - len(new_customers))
        self.new_products_count = len(new_items)
        self.matched_products_count = max(0, len(existing_products) - len(new_items))
        self.has_errors = has_err
        self.is_tested = True
        self.state = 'draft' if has_err else 'tested'

        # Cache parsed data in JSON
        self.parsed_data_json = json.dumps(invoices)

        # Build Rich HTML Verification Report
        report_parts = []
        if not has_err:
            report_parts.append("""
                <div class="alert alert-success d-flex align-items-center mb-3" style="border-radius: 8px; border-left: 5px solid #28a745;">
                    <div>
                        <h4 class="alert-heading mb-1 fw-bold text-success">
                            <i class="fa fa-check-circle me-2"></i> Verification Passed Successfully!
                        </h4>
                        <p class="mb-0 text-muted">All invoice structures and line items validated. Ready for import.</p>
                    </div>
                </div>
            """)
        else:
            report_parts.append(f"""
                <div class="alert alert-danger d-flex align-items-center mb-3" style="border-radius: 8px; border-left: 5px solid #dc3545;">
                    <div>
                        <h4 class="alert-heading mb-1 fw-bold text-danger">
                            <i class="fa fa-exclamation-triangle me-2"></i> Found {len(validation_errors)} Validation Errors
                        </h4>
                        <p class="mb-0 text-muted">Please correct the data rows below before proceeding with the import.</p>
                    </div>
                </div>
            """)

        # Metric Badges
        report_parts.append(f"""
            <div class="row g-2 mb-3 text-center">
                <div class="col-sm-3">
                    <div class="p-2 border rounded bg-white shadow-sm">
                        <div class="text-muted small fw-bold text-uppercase">Invoices</div>
                        <div class="fs-4 fw-bold text-primary">{self.invoices_count:,}</div>
                    </div>
                </div>
                <div class="col-sm-3">
                    <div class="p-2 border rounded bg-white shadow-sm">
                        <div class="text-muted small fw-bold text-uppercase">Line Items</div>
                        <div class="fs-4 fw-bold text-info">{self.lines_count:,}</div>
                    </div>
                </div>
                <div class="col-sm-3">
                    <div class="p-2 border rounded bg-white shadow-sm">
                        <div class="text-muted small fw-bold text-uppercase">Total Sales Value</div>
                        <div class="fs-4 fw-bold text-success">${self.total_amount:,.2f}</div>
                    </div>
                </div>
                <div class="col-sm-3">
                    <div class="p-2 border rounded bg-white shadow-sm">
                        <div class="text-muted small fw-bold text-uppercase">Tenant Binding</div>
                        <div class="fs-6 fw-bold text-dark text-truncate" title="{target_tenant.name}">{target_tenant.name}</div>
                    </div>
                </div>
            </div>
        """)

        # Detailed Entity Reconciliation Card
        cust_auto_badge = '<span class="badge bg-success ms-1">Auto-create Enabled</span>' if self.auto_create_customer else '<span class="badge bg-warning ms-1">Requires Existing</span>'
        prod_auto_badge = '<span class="badge bg-success ms-1">Auto-create Enabled</span>' if self.auto_create_product else '<span class="badge bg-warning ms-1">Requires Existing</span>'

        report_parts.append(f"""
            <div class="card border-0 shadow-sm mb-3">
                <div class="card-header bg-light py-2 fw-bold text-dark">
                    <i class="fa fa-database me-1"></i> Database Matching Summary
                </div>
                <div class="card-body py-2">
                    <div class="row">
                        <div class="col-md-6 mb-2">
                            <div class="d-flex justify-content-between align-items-center">
                                <span><strong>Products in File:</strong></span>
                                <span>{len(existing_products)} Matched, <strong class="text-primary">{len(new_items)} New</strong> {prod_auto_badge}</span>
                            </div>
                            {"<small class='text-muted'>Sample new items: " + ", ".join(list(new_items)[:4]) + "...</small>" if new_items else "<small class='text-success'>All items matched in catalog!</small>"}
                        </div>
                        <div class="col-md-6 mb-2">
                            <div class="d-flex justify-content-between align-items-center">
                                <span><strong>Customers in File:</strong></span>
                                <span>{len(existing_customers)} Matched, <strong class="text-primary">{len(new_customers)} New</strong> {cust_auto_badge}</span>
                            </div>
                            {"<small class='text-muted'>Sample new customers: " + ", ".join(list(new_customers)[:4]) + "...</small>" if new_customers else "<small class='text-success'>All customers matched!</small>"}
                        </div>
                    </div>
                </div>
            </div>
        """)

        # Error Details
        if validation_errors:
            error_list_html = "".join([f"<li class='text-danger'>{err}</li>" for err in validation_errors[:15]])
            if len(validation_errors) > 15:
                error_list_html += f"<li class='text-muted'>... and {len(validation_errors)-15} more errors.</li>"
            report_parts.append(f"""
                <div class="card border-danger shadow-sm mb-3">
                    <div class="card-header bg-danger text-white py-2 fw-bold">
                        <i class="fa fa-times-circle me-1"></i> Errors to Fix in Spreadsheet
                    </div>
                    <div class="card-body py-2">
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
        """Execute the actual import of tested and verified sales invoices."""
        self.ensure_one()
        if not self.is_tested or self.has_errors:
            raise UserError(_("You must run 'Test & Verify Data' and resolve any errors before importing."))

        if not self.parsed_data_json:
            raise UserError(_("No verified data cache found. Please run 'Test & Verify Data' again."))

        invoices_data = json.loads(self.parsed_data_json)
        if not invoices_data:
            raise UserError(_("No invoices to import."))

        target_tenant = self.tenant_id or self.env.user.tenant_id
        if not target_tenant:
            target_tenant = self.env['havanoposdesk.tenant'].search([], limit=1)

        # 1. Ensure/resolve customer cache
        Customer = self.env['havanoposdesk.customer'].sudo()
        cust_cache = {
            c.name.strip().lower(): c.id
            for c in Customer.search([('tenant_id', '=', target_tenant.id)])
        }
        for inv in invoices_data:
            cname = (inv.get('customer_name') or 'Walk-in Customer').strip()
            ckey = cname.lower()
            if ckey not in cust_cache:
                if self.auto_create_customer:
                    new_c = Customer.create({
                        'name': cname,
                        'tenant_id': target_tenant.id
                    })
                    cust_cache[ckey] = new_c.id
                else:
                    first_c = Customer.search([('tenant_id', '=', target_tenant.id)], limit=1)
                    cust_cache[ckey] = first_c.id if first_c else False

        # 2. Ensure/resolve product cache
        Product = self.env['havanoposdesk.product'].sudo()
        prod_cache = {
            p.name.strip().lower(): p.id
            for p in Product.search([('tenant_id', '=', target_tenant.id)])
        }
        for inv in invoices_data:
            for l in inv.get('lines', []):
                pname = (l.get('item') or '').strip()
                pkey = pname.lower()
                if pkey and pkey not in prod_cache:
                    if self.auto_create_product:
                        new_p = Product.create({
                            'name': pname,
                            'tenant_id': target_tenant.id,
                            'selling_price': l.get('price', 0.0),
                            'store_ids': [(4, inv.get('store_id'))] if inv.get('store_id') else False
                        })
                        prod_cache[pkey] = new_p.id
                    else:
                        first_p = Product.search([('tenant_id', '=', target_tenant.id)], limit=1)
                        prod_cache[pkey] = first_p.id if first_p else False

        # 3. Resolve cash account
        Account = self.env['havanoposdesk.account'].sudo()
        cash_account_id = self.account_id.id if self.account_id else False
        if not cash_account_id and self.payment_status == 'cash':
            acc = Account.search([
                ('tenant_id', '=', target_tenant.id),
                ('type', 'in', ['Cash', 'Bank']),
                ('is_on_account', '=', False)
            ], limit=1)
            cash_account_id = acc.id if acc else False

        # 4. Resolve default store
        Store = self.env['havanoposdesk.store'].sudo()
        default_store = self.store_id or Store.search([('tenant_id', '=', target_tenant.id)], limit=1)
        fallback_store_id = default_store.id if default_store else False

        currency_id_val = self.currency_id.id if self.currency_id else (
            target_tenant.currency_id.id if target_tenant.currency_id else self.env.company.currency_id.id
        )

        # 5. Batch create invoices
        SaleOrder = self.env['havanoposdesk.sale'].sudo()
        created_sale_ids = []
        batch_size = 300
        current_batch_vals = []

        total_to_import = len(invoices_data)
        _logger.info("Beginning batch import of %s sales invoices for tenant %s", total_to_import, target_tenant.name)

        for inv in invoices_data:
            cust_id = cust_cache.get((inv.get('customer_name') or '').strip().lower(), False)
            store_id_val = inv.get('store_id') or fallback_store_id

            lines_vals = []
            for l in inv.get('lines', []):
                pid = prod_cache.get((l.get('item') or '').strip().lower(), False)
                if not pid:
                    continue
                lines_vals.append((0, 0, {
                    'product_id': pid,
                    'name': l.get('item', 'Item'),
                    'accepted_qty': l.get('qty', 1.0),
                    'rate': l.get('price', 0.0),
                    'tenant_id': target_tenant.id,
                }))

            if not lines_vals:
                continue

            sale_vals = {
                'name': 'New',
                'local_invoice_id': inv.get('local_id'),
                'tenant_id': target_tenant.id,
                'store_id': store_id_val,
                'customer': cust_id,
                'date': inv.get('date'),
                'currency_id': currency_id_val,
                'payment_status': self.payment_status,
                'account_id': cash_account_id if self.payment_status == 'cash' else False,
                'state': 'done',
                'line_ids': lines_vals,
            }
            current_batch_vals.append(sale_vals)

            if len(current_batch_vals) >= batch_size:
                sales = SaleOrder.create(current_batch_vals)
                created_sale_ids.extend(sales.ids)
                current_batch_vals = []
                self.env.cr.commit()

        if current_batch_vals:
            sales = SaleOrder.create(current_batch_vals)
            created_sale_ids.extend(sales.ids)
            self.env.cr.commit()

        _logger.info("Completed import: %s sales invoices created.", len(created_sale_ids))
        self.state = 'imported'

        # Return action to view imported sales
        return {
            'name': _('Imported Sales Invoices'),
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.sale',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_sale_ids)],
            'target': 'current',
        }
