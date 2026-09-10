# Havano POS Desk Odoo

Backend API module for Havano POS (Desktop & Mobile).

### Quick Links
- **API Docs**: [API_DOCUMENTATION.md](file:///c:/Program%20Files/Odoo%2019.0.20260803/server/addons/custom-addons/havanoposdesk_odoo/API_DOCUMENTATION.md)
- **Changelog**: [CHANGELOG.md](file:///c:/Program%20Files/Odoo%2019.0.20260803/server/addons/custom-addons/havanoposdesk_odoo/CHANGELOG.md)

### Key Endpoints
1. `POST /api/method/saas_api.www.api.login` - Auth & multi-store cashier permissions.
2. `GET /api/user/shops` - Filtered shops with default pricelists.
3. `POST /api/user/select-shop` - Bind device hardware ID to terminal.
4. `GET /api/method/havano_pos_integration.api.get_products` - Product sync with advanced pricing.
5. `POST /saas_api/make_sale` - POS invoice sync.
