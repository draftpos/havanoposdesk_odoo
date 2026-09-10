# core/models/fiscal_service.py - ZIMRA Cloud Fiscalization API Integration

import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

HS_CODE_DEFAULT = "99999999"


class HavanoZimraCloudService:
    """
    Service wrapper for Havano ZIMRA Cloud Fiscalization API.
    Handles 2-tier authentication (CSRF Token + API Key/Secret Token header),
    xml item payload generation with inclusive VAT, and offline fallback mode.
    """

    def __init__(self, env=None):
        self.env = env

    def fetch_csrf_token(self, base_url: str, session: requests.Session) -> tuple:
        token_url = f"{base_url.rstrip('/')}/api/method/havanozimracloud.api.token"
        try:
            _logger.info("[ZIMRA] Fetching CSRF Token from %s", token_url)
            resp = session.post(token_url, timeout=6)
            if resp.status_code != 200:
                return False, f"Token request failed HTTP {resp.status_code}: {resp.text}"
            res_json = resp.json()
            csrf_token = res_json.get("message") or res_json.get("token") or res_json.get("csrf_token")
            if not csrf_token:
                return False, f"Invalid token format in response: {resp.text}"
            return True, str(csrf_token)
        except Exception as e:
            return False, f"CSRF token connection error: {e}"

    def ping_device(self, settings_record) -> dict:
        tenant = getattr(settings_record, 'tenant_id', None)
        base_url = ((getattr(settings_record, 'fiscal_base_url', '') or (tenant and tenant.fiscal_base_url) or '')).strip()
        api_key = ((getattr(settings_record, 'fiscal_api_key', '') or (tenant and tenant.fiscal_api_key) or '')).strip()
        api_secret = ((getattr(settings_record, 'fiscal_api_secret', '') or (tenant and tenant.fiscal_api_secret) or '')).strip()
        device_sn = ((getattr(settings_record, 'fiscal_device_sn', '') or (tenant and tenant.fiscal_device_sn) or '')).strip()

        if not base_url:
            return {'success': False, 'error': 'Base URL is required'}

        session = requests.Session()
        ok, token_or_err = self.fetch_csrf_token(base_url, session)
        if not ok:
            return {'success': False, 'error': token_or_err}

        csrf_token = token_or_err
        ping_url = f"{base_url.rstrip('/')}/api/method/havanozimracloud.api.pingzimra"
        headers = {
            "X-Frappe-CSRF-Token": csrf_token,
            "Authorization": f"token {api_key}:{api_secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        payload = {
            "device_sn": str(device_sn)
        }

        try:
            _logger.info("[ZIMRA] Pinging device %s at %s", device_sn, ping_url)
            resp = session.post(ping_url, data=payload, headers=headers, timeout=6)
            if resp.status_code != 200:
                return {'success': False, 'error': f"HTTP {resp.status_code}: {resp.text}"}

            res_json = resp.json()
            msg = res_json.get("message", {})
            if isinstance(msg, dict) and msg.get("status") == "success":
                return {'success': True, 'data': msg}
            else:
                return {'success': True, 'data': res_json}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def build_items_xml(self, sale_lines, is_vat_registered: bool = False) -> str:
        root = ET.Element("ITEMS")
        for idx, line in enumerate(sale_lines, 1):
            item_elem = ET.SubElement(root, "ITEM")

            qty = abs(float(line.accepted_qty or 1.0))
            price = abs(float(line.rate or 0.0))
            total = abs(float(line.amount or (qty * price)))

            # Tax rate calculation
            if is_vat_registered:
                taxes = line.tax_ids
                raw_rate = sum(t.rate for t in taxes) if taxes else 15.0
            else:
                raw_rate = 0.0

            if raw_rate <= 0.005:
                vat_name = "EXEMPT"
                vat_amount = 0.0
                vatr_val = "0.00"
            else:
                vat_name = "VAT"
                tax_rate = raw_rate if raw_rate > 0 else 15.0
                # Inclusive VAT calculation formula
                vat_amount = round(total - (total / (1.0 + (tax_rate / 100.0))), 2)
                # Format VATR as decimal proportion (e.g. 0.155 for 15.5% or 0.15 for 15%)
                vatr_decimal = tax_rate / 100.0
                vatr_val = f"{vatr_decimal:.3f}".rstrip('0').rstrip('.')

            product = line.product_id
            item_name = str(product.name if product else "Item")[:100]

            code_val = (product and (product.item_code or product.part_no)) or ""
            raw_code = ''.join(c for c in str(code_val) if c.isdigit())
            if len(raw_code) == 8:
                item_code = raw_code
            else:
                item_code = HS_CODE_DEFAULT

            ET.SubElement(item_elem, "HH").text = str(idx)
            ET.SubElement(item_elem, "ITEMCODE").text = item_code
            ET.SubElement(item_elem, "ITEMNAME").text = item_name
            ET.SubElement(item_elem, "ITEMNAME2").text = item_name
            ET.SubElement(item_elem, "QTY").text = f"{qty:.2f}"
            ET.SubElement(item_elem, "PRICE").text = f"{price:.2f}"
            ET.SubElement(item_elem, "TOTAL").text = f"{total:.2f}"
            ET.SubElement(item_elem, "VAT").text = f"{vat_amount:.2f}"
            ET.SubElement(item_elem, "VATR").text = vatr_val
            ET.SubElement(item_elem, "VNAME").text = vat_name[:20]

        return ET.tostring(root, encoding="unicode")

    def process_sale_fiscalization(self, sale) -> dict:
        """
        Fiscalize a sale record using store-specific (or tenant fallback) configuration.
        """
        store = sale.store_id
        tenant = sale.tenant_id

        # Check if fiscalization is enabled on store or tenant
        store_enabled = store and store.enable_fiscalization
        tenant_enabled = tenant and tenant.enable_fiscalization
        if not (store_enabled or tenant_enabled):
            return {'status': 'not_required', 'error': 'Fiscalization is not enabled'}

        # Field-by-field fallback hierarchy: Store value -> Tenant (Global) value
        base_url = ((store and store.fiscal_base_url) or (tenant and tenant.fiscal_base_url) or '').strip()
        api_key = ((store and store.fiscal_api_key) or (tenant and tenant.fiscal_api_key) or '').strip()
        api_secret = ((store and store.fiscal_api_secret) or (tenant and tenant.fiscal_api_secret) or '').strip()
        device_sn = ((store and store.fiscal_device_sn) or (tenant and tenant.fiscal_device_sn) or '').strip()

        if not base_url or not device_sn:
            return {'status': 'failed', 'error': 'ZIMRA Base URL and Device Serial Number (EFD SN) are required'}

        invoice_number = sale.name
        currency = (sale.currency_id.name or 'USD').upper()
        if currency in ('ZWD', 'ZWL', 'ZWG'):
            currency = 'ZIG'

        customer_name = sale.customer.name if sale.customer else "Walk-in Customer"
        customer_tin = (getattr(sale.customer, 'tin', '') or '').strip() if sale.customer else ''
        customer_vat = (getattr(sale.customer, 'vat', '') or '').strip() if sale.customer else ''
        customer_address = (getattr(sale.customer, 'address', '') or '').strip() if sale.customer else ''
        customer_phone = (getattr(sale.customer, 'phone', '') or '').strip() if sale.customer else ''
        customer_city = (getattr(sale.customer, 'city', '') or '').strip() if sale.customer else ''
        customer_email = (getattr(sale.customer, 'email', '') or '').strip() if sale.customer else ''

        if not customer_tin or len(customer_tin) != 10:
            customer_tin = "111111111"

        if not customer_vat or len(customer_vat) != 9:
            customer_vat = "000000000"
            
        if not customer_address:
            customer_address = "123 Default Street"
            
        if not customer_phone:
            customer_phone = "0000000000"
            
        if not customer_city:
            customer_city = "Default City"

        if not customer_email:
            customer_email = "walkin@example.com"

        tendered = abs(float(sale.amount_total or 0.0))
        invoice_flag = "1" if sale.is_return else "0"

        original_invoice_no = ""
        global_invoice_no = ""
        if sale.is_return and sale.return_id:
            original_invoice_no = sale.return_id.name or ""
            global_invoice_no = sale.return_id.fiscal_global_no or ""

        is_vat_registered = bool(getattr(store, 'is_vat_registered', False) or getattr(tenant, 'is_vat_registered', False))
        items_xml = self.build_items_xml(sale.line_ids, is_vat_registered=is_vat_registered)

        session = requests.Session()
        ok, token_or_err = self.fetch_csrf_token(base_url, session)
        if not ok:
            _logger.warning("[ZIMRA] Could not fetch token: %s", token_or_err)
            return {'status': 'failed', 'error': f"ZIMRA CSRF Token Error: {token_or_err}"}

        csrf_token = token_or_err
        send_url = f"{base_url.rstrip('/')}/api/method/havanozimracloud.api.sendinvoice"
        headers = {
            "X-Frappe-CSRF-Token": csrf_token,
            "Authorization": f"token {api_key}:{api_secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        # ZIMRA expects add_customer="1" to display buyer details on the fiscal invoice
        is_walkin = not sale.customer or (sale.customer.name or '').strip().lower() in ('walk-in customer', 'walk in', 'walk-in', 'walkin')
        add_customer_flag = "0" if is_walkin else "1"

        payload = {
            "device_sn": str(device_sn),
            "add_customer": add_customer_flag,
            "invoice_flag": str(invoice_flag),
            "currency": str(currency),
            "invoice_number": str(invoice_number),
            "customer_name": str(customer_name),
            "trade_name": str(customer_name),
            "customer_vat_number": str(customer_vat),
            "customer_address": str(customer_address),
            "customer_telephone_number": str(customer_phone),
            "customer_tin": str(customer_tin),
            "customer_province": "Default Province",
            "customer_street": str(customer_address),
            "customer_houseNo": "1",
            "customer_city": str(customer_city),
            "customer_email": str(customer_email),
            "invoice_comment": "",
            "original_invoice_no": str(original_invoice_no),
            "global_invoice_no": str(global_invoice_no),
            "tendered": f"{tendered:.2f}",
            "items_xml": items_xml,
        }

        print("\n" + "="*80, flush=True)
        print(f"[ZIMRA API REQUEST] -> {send_url}", flush=True)
        print(f"[ZIMRA API HEADERS] -> {headers}", flush=True)
        print(f"[ZIMRA API PAYLOAD] ->", flush=True)
        for k, v in payload.items():
            print(f"   {k}: {v}", flush=True)
        print("="*80 + "\n", flush=True)

        _logger.info("[ZIMRA API REQUEST] URL: %s | Headers: %s | Payload: %s", send_url, headers, payload)

        try:
            resp = session.post(send_url, data=payload, headers=headers, timeout=10)
            print("\n" + "="*80, flush=True)
            print(f"[ZIMRA API RESPONSE] Status: {resp.status_code}", flush=True)
            print(f"[ZIMRA API RESPONSE BODY] -> {resp.text}", flush=True)
            print("="*80 + "\n", flush=True)

            _logger.info("[ZIMRA API RESPONSE] Status: %s | Text: %s", resp.status_code, resp.text)

            if resp.status_code != 200:
                _logger.warning("[ZIMRA] Non-200 HTTP response (%s): %s", resp.status_code, resp.text)
                return {'status': 'failed', 'error': resp.text}

            res_json = resp.json()
            msg = res_json.get("message", res_json)

            if isinstance(msg, dict):
                qr_code = str(msg.get("QRcode") or msg.get("qr_code") or "")
                ver_code = str(msg.get("VerificationCode") or msg.get("verification_code") or "")
                device_id = str(msg.get("DeviceID") or msg.get("device_id") or "")
                fiscal_day = str(msg.get("FiscalDay") or msg.get("fiscal_day") or "")
                receipt_counter = int(msg.get("receiptCounter") or msg.get("receipt_counter") or 0)
                global_no = str(msg.get("receiptGlobalNo") or msg.get("receipt_global_no") or "")

                if qr_code or ver_code or global_no:
                    return {
                        'status': 'fiscalized',
                        'qr_code': qr_code,
                        'verification_code': ver_code,
                        'receipt_counter': receipt_counter,
                        'global_no': global_no,
                        'device_id': device_id,
                        'device_serial': device_sn,
                        'fiscal_day': fiscal_day,
                        'error': False
                    }

            return {'status': 'failed', 'error': resp.text}

        except Exception as e:
            _logger.exception("[ZIMRA] Exception during invoice submission: %s", e)
            return {'status': 'failed', 'error': f"ZIMRA Connection Error: {e}"}

    def _process_offline(self, sale, device_sn: str) -> dict:
        """
        Generate local SHA-256 signature hash and URL for offline fallback mode.
        """
        try:
            date_str = datetime.now().strftime("%Y%m%d%H%M%S")
            raw_str = f"{device_sn}{date_str}{sale.id}{sale.amount_total:.2f}"
            sig_hash = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()[:16].upper()

            local_url = f"https://zimra.gov.zw/verify?sn={device_sn}&no={sale.id}&hash={sig_hash}"

            return {
                'status': 'PENDING_SYNC',
                'qr_code': local_url,
                'verification_code': sig_hash,
                'receipt_counter': 0,
                'global_no': str(sale.id),
                'device_id': 'OFFLINE',
                'device_serial': device_sn,
                'fiscal_day': datetime.now().strftime("%Y-%m-%d"),
                'error': False
            }
        except Exception as e:
            return {
                'status': 'failed',
                'error': f"Offline fallback exception: {e}"
            }


_service_instance = None


def get_zimra_service(env=None) -> HavanoZimraCloudService:
    global _service_instance
    if _service_instance is None or env is not None:
        _service_instance = HavanoZimraCloudService(env)
    return _service_instance
