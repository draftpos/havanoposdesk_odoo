from odoo import http
from odoo.http import request
import csv
import io

class ProductImportTemplateController(http.Controller):

    @http.route('/havanoposdesk_odoo/product_template.csv', type='http', auth='user')
    def download_product_template(self, **kwargs):
        tenant_id = request.env.user.tenant_id.id
        tenant = request.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else request.env['havanoposdesk.tenant']
        
        # Get next sequence without consuming it
        prefix = getattr(tenant, 'prod_seq_prefix', '') or ''
        next_val = getattr(tenant, 'prod_seq_next', 1) or 1
        padding = getattr(tenant, 'prod_seq_padding', 0) or 0
        seq_str = str(next_val)
        if padding > 0:
            seq_str = seq_str.zfill(padding)
        next_code = f"{prefix}{seq_str}"
        
        # Prepare CSV data
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
        
        # Write headers
        headers = [
            "Product Name", "Product Code", "Barcode", "Cost price", "Category", 
            "UOM", "Active", 
            "Variants / Variant Name", "Variants / Cost Price", "Variants / Sell Price", "Variants / Allocate QTY (from base stock)",
            "Advanced Prices / Store", 
            "Advanced Prices / Pricelist", "Advanced Prices / UoM Name", 
            "Advanced Prices / Qty to be Sold", "Advanced Prices / Initial Qty", "Advanced Prices / Price"
        ]
        writer.writerow(headers)
        
        info_msg = f"Leave this column BLANK! Next auto-assigned code will be {next_code}"
        
        # Write Example Product 1: With Variants
        writer.writerow([
            "Example Variant Product (e.g. T-Shirt)", info_msg, "89012340", 10.00, "Beverages", "Each", 1, 
            "Black - Size M", 10.00, 15.00, 20,
            "", "", "", "", "", ""
        ])
        writer.writerow([
            "", "", "", "", "", "", "", 
            "White - Size L", 10.00, 16.00, 15,
            "", "", "", "", "", ""
        ])
        
        # Write Example Product 2: Standard Product with Advanced Prices
        writer.writerow([
            "Example Standard Product", info_msg, "89012345", 1.00, "Beverages", "Each", 1, 
            "", "", "", "",
            "Main Store", "Retail", "Each", 1, 50, 1.50
        ])
        writer.writerow([
            "", "", "", "", "", "", "", 
            "", "", "", "",
            "Main Store", "Wholesale", "Box", 12, 10, 15.00
        ])
        
        csv_data = output.getvalue()
        output.close()
        
        headers = [
            ('Content-Type', 'text/csv'),
            ('Content-Disposition', 'attachment; filename="product_import_template.csv"'),
        ]
        return request.make_response(csv_data, headers=headers)
