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
            "UOM", "Active", "Advanced Prices / Store", 
            "Advanced Prices / Pricelist", "Advanced Prices / UOM", 
            "Advanced Prices / Qty to be Sold", "Advanced Prices / Initial Qty", "Advanced Prices / Price"
        ]
        writer.writerow(headers)
        
        # Write example row
        info_msg = f"Leave this column BLANK! Next auto-assigned code will be {next_code}"
        writer.writerow([
            "Example Product 1", info_msg, "89012345", 1.00, "Beverages", "Each", 1, 
            "Main Store", "Retail", "Each", 1, 50, 1.50
        ])
        
        # Write second advanced price line for the same product
        writer.writerow([
            "", "", "", "", "", "", "", 
            "Main Store", "Wholesale", "Box", 12, 10, 15.00
        ])
        
        csv_data = output.getvalue()
        output.close()
        
        headers = [
            ('Content-Type', 'text/csv'),
            ('Content-Disposition', 'attachment; filename="product_import_template.csv"'),
        ]
        return request.make_response(csv_data, headers=headers)
