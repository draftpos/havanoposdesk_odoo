# Havano POS Desk Odoo - API Reference

## 1. Authentication & Users
- **Header**: `Authorization: Bearer <token>`

### `POST /api/method/saas_api.www.api.login`
**Request:**
```json
{ "usr": "cashier@email.com", "pwd": "pass", "pin": "1234" }
```
**Response (200):**
```json
{
  "message": {
    "user": "cashier@email.com",
    "role": "user",
    "warehouse": "Dreamwiseagency, store 2",
    "shops": [
      { "id": 2, "name": "Dreamwiseagency" },
      { "id": 3, "name": "store 2" }
    ],
    "store_ids": [2, 3],
    "pin": "1234",
    "token": "<token>"
  }
}
```

---

## 2. Shops & Terminals

### `GET /api/user/shops`
*Returns shops accessible to the logged-in user (filtered by `store_ids` for cashiers).*

**Response (200):**
```json
[
  {
    "id": 3,
    "name": "store 2",
    "default_pricelist_id": 3,
    "default_pricelist_name": "Retail 2",
    "pricelist_names": ["Retail 2"],
    "terminals": [
      { "id": 2, "name": "Pos 2", "status": "available", "device_hardware_id": "HW-2002" }
    ]
  }
]
```

### `POST /api/user/select-shop`
**Request:**
```json
{ "shop_id": 3, "terminal_id": 2, "device_hardware_id": "HW-2002", "app_version": "v2.0.8.37" }
```

---

## 3. Products & Pricing

### `GET /api/products/`
*Returns all active products for the authenticated user and tenant, including variant details.*

**Response (200):**
```json
[
  {
    "id": 42,
    "name": "Men's Polo Shirt",
    "item_code": "POLO-001",
    "barcode": "123456789012",
    "buying_price": 10.0,
    "selling_price": 20.0,
    "color_hex": "#1e40af",
    "image_url": "/web/image/havanoposdesk.product/42/image_1920",
    "track_qty": true,
    "is_bundle": 0,
    "is_stock_item": 1,
    "is_sales_item": 1,
    "sellbyprice": 0,
    "sell_by_price": 0,
    "category": 1,
    "uom": 1,
    "tenant_id": 1,
    "store_id": 2,
    "is_variant": 1,
    "variants": [
      {
        "id": 101,
        "name": "Red / Small",
        "cost_price": 10.0,
        "selling_price": 20.0,
        "on_hand_qty": 50.0
      },
      {
        "id": 102,
        "name": "Blue / Medium",
        "cost_price": 10.0,
        "selling_price": 22.0,
        "on_hand_qty": 40.0
      }
    ]
  }
]
```

### `POST /api/products/`
*Creates a new product with optional product variants via JSON payload.*

**Request:**
```json
{
  "name": "Men's Polo Shirt",
  "item_code": "POLO-001",
  "barcode": "123456789012",
  "buying_price": 10.0,
  "selling_price": 20.0,
  "color_hex": "#1e40af",
  "track_qty": true,
  "category": 1,
  "uom": 1,
  "store_id": 2,
  "is_variant": 1,
  "variants": [
    {
      "name": "Red / Small",
      "cost_price": 10.0,
      "selling_price": 20.0,
      "allocate_qty": 50.0
    },
    {
      "name": "Blue / Medium",
      "cost_price": 10.0,
      "selling_price": 22.0,
      "allocate_qty": 40.0
    }
  ]
}
```
- Set `"is_variant": 1` (or `"is_variant_": 1`) when creating a product with variants.
- Each variant entry accepts `name` (required), `cost_price` (or `buying_price`), `selling_price` (or `sell_price`), and initial quantity via `allocate_qty` (or `initial_qty` / `on_hand_qty` / `qty`).

**Response (201):**
```json
{
  "id": 42,
  "name": "Men's Polo Shirt",
  "item_code": "POLO-001",
  "barcode": "123456789012",
  "buying_price": 10.0,
  "selling_price": 20.0,
  "color_hex": "#1e40af",
  "image_url": "/web/image/havanoposdesk.product/42/image_1920",
  "track_qty": true,
  "sellbyprice": 0,
  "sell_by_price": 0,
  "category": 1,
  "uom": 1,
  "tenant_id": 1,
  "store_id": 2,
  "is_variant": 1,
  "variants": [
    {
      "id": 101,
      "name": "Red / Small",
      "cost_price": 10.0,
      "selling_price": 20.0,
      "on_hand_qty": 50.0
    },
    {
      "id": 102,
      "name": "Blue / Medium",
      "cost_price": 10.0,
      "selling_price": 22.0,
      "on_hand_qty": 40.0
    }
  ]
}
```

### `GET /api/method/havano_pos_integration.api.get_products?shop_id=3`
**Response (200):**
```json
{
  "message": {
    "products": [
      {
        "itemcode": "103",
        "itemname": "Stock 4",
        "uom": { "stock_uom": "Each" },
        "selling_price": 89.0,
        "prices": [
          { "priceName": "Retail 2", "price": 89.0, "uom": "Each", "type": "selling", "store": "store 2" },
          { "priceName": "Retail", "price": 56.0, "uom": "Each", "type": "selling", "store": "Dreamwiseagency" }
        ],
        "warehouses": [{ "warehouse": "store 2", "qtyOnHand": 25.0 }],
        "taxes": [{ "maximum_net_rate": 0.0, "tax_category": "ZERO RATED" }]
      }
    ],
    "total_count": 1
  }
}
```

---

## 4. Sales Sync

### `POST /saas_api/make_sale`
**Request:**
```json
{
  "pos_invoice": {
    "pos_profile": "Pos 2",
    "store_id": 3,
    "price_list": "Retail 2",
    "customer": "Cash Customer",
    "grand_total": 89.0,
    "items": [
      { "item_code": "103", "qty": 1.0, "rate": 89.0, "amount": 89.0 }
    ],
    "payments": [
      { "mode_of_payment": "Cash", "amount": 89.0, "currency": "USD" }
    ]
  }
}
```
