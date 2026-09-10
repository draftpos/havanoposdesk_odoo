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
