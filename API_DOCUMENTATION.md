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

---

## 5. Expenses & Claims

- **Header**: `Authorization: Bearer <token>`
- **Content-Type**: `application/json`

### `GET /api/resource/Expense Claim Type`
*Returns the available expense categories/types (active accounts of type `Expense`).*

**Response (200):**
```json
{
  "data": [
    {
      "name": "Shop Utilities",
      "expense_type": "Shop Utilities",
      "default_account": "Shop Utilities",
      "description": "Expense Account"
    },
    {
      "name": "Refreshments & Meals",
      "expense_type": "Refreshments & Meals",
      "default_account": "Refreshments & Meals",
      "description": "Expense Account"
    }
  ]
}
```

### `POST /api/resource/Expense Claim Type`
*Creates a new expense type / category on the fly.*

**Request:**
```json
{
  "expense_type": "Cleaning Supplies"
}
```

**Response (200):**
```json
{
  "data": {
    "name": "Cleaning Supplies",
    "expense_type": "Cleaning Supplies"
  }
}
```

### `POST /api/resource/Expense Claim`
*Submits an expense from the POS terminal. Supports single expense objects or batch lists.*

**Request (Single Expense):**
```json
{
  "expense_type": "Shop Utilities",
  "amount": 25.50,
  "description": "Electricity token",
  "is_paid": true,
  "account": "Cash",
  "store_id": 3,
  "shift_id": 12
}
```

**Request (Batch Expenses):**
```json
{
  "expenses": [
    {
      "expense_type": "Shop Utilities",
      "amount": 25.50,
      "description": "Electricity token",
      "is_paid": true,
      "account": "Cash",
      "store_id": 3,
      "shift_id": 12
    },
    {
      "expense_type": "Refreshments & Meals",
      "amount": 10.00,
      "description": "Milk and coffee for staff",
      "is_paid": true
    }
  ]
}
```

**Response (200):**
```json
{
  "data": {
    "name": "EXP-2026-00012",
    "status": "Posted",
    "expenses": [
      {
        "id": 45,
        "name": "EXP-2026-00012",
        "status": "Posted"
      }
    ],
    "requires_approval": false
  }
}
```

### `GET /api/resource/Expense Claim`
*Lists recorded expenses for the user's active tenant and store.*

**Response (200):**
```json
{
  "data": [
    {
      "id": 45,
      "name": "EXP-2026-00012",
      "store": "store 2",
      "expense_type": "Shop Utilities",
      "amount": 25.50,
      "total_claimed_amount": 25.50,
      "is_paid": true,
      "paid_status": "Paid",
      "account": "Cash",
      "employee": "Cashier Name",
      "posting_date": "2026-09-09",
      "state": "Posted",
      "status": "Posted",
      "submitted_by_cashier": true,
      "shift_id": 12,
      "shift_name": "SHIFT/2026/09/0004",
      "company": "store 2"
    }
  ]
}
```

### `POST /api/method/saas_api.www.api.approve_expense`
*Manager approval for pending expenses (deducts cash from payment account upon approval).*

**Request:**
```json
{
  "expense_id": 45
}
```

**Response (200):**
```json
{
  "message": {
    "status": "success",
    "expense": {
      "id": 45,
      "name": "EXP-2026-00012",
      "state": "Posted"
    }
  }
}
```

### `POST /api/method/saas_api.www.api.reject_expense`
*Manager rejection for pending expenses.*

**Request:**
```json
{
  "expense_id": 45
}
```

**Response (200):**
```json
{
  "message": {
    "status": "success",
    "expense": {
      "id": 45,
      "name": "EXP-2026-00012",
      "state": "Rejected"
    }
  }
}
```



---

## 6. Stock & Inventory Management

- **Header**: `Authorization: Bearer <token>`
- **Content-Type**: `application/json`

### `GET /api/method/erpnext.stock.utils.get_stock_balance`
*Retrieves the current real-time stock on hand for an item in a specific warehouse/store.*

**Query Parameters:**
- `item_code`: The item code / barcode (e.g. `103`)
- `warehouse`: The name of the store / warehouse (e.g. `store 2`)

**Request Example:**
`GET /api/method/erpnext.stock.utils.get_stock_balance?item_code=103&warehouse=store%202`

**Response (200):**
```json
{
  "message": 25.0
}
```

---

### `POST /api/resource/Stock Entry`
*Creates and records a Stock Entry (Material Transfer between stores, Material Receipt into store, or Material Issue out of store). Automatically updates warehouse stock valuation and the stock ledger upon submission.*

**Supported `stock_entry_type` values:**
- `"Material Transfer"` (requires `from_warehouse` and `to_warehouse`)
- `"Material Receipt"` (requires `to_warehouse`)
- `"Material Issue"` (requires `from_warehouse`)

**Request (Material Transfer between Warehouses):**
```json
{
  "stock_entry_type": "Material Transfer",
  "from_warehouse": "Dreamwiseagency",
  "to_warehouse": "store 2",
  "posting_date": "2026-09-09",
  "remarks": "Inter-branch inventory transfer from main depot",
  "docstatus": 1,
  "items": [
    {
      "item_code": "103",
      "qty": 10.0,
      "uom": "Each",
      "basic_rate": 45.00
    }
  ]
}
```

**Response (200):**
```json
{
  "data": {
    "name": "STE-00015",
    "stock_entry_type": "Material Transfer",
    "posting_date": "2026-09-09 00:00:00",
    "from_warehouse": "Dreamwiseagency",
    "to_warehouse": "store 2",
    "remarks": "Inter-branch inventory transfer from main depot",
    "docstatus": 1
  }
}
```

---

### `GET /api/resource/Stock Entry`
*Lists recorded stock entries/transfers scoped to the user's accessible stores and tenant.*

**Optional Query Parameters:**
- `filters`: JSON array e.g. `[["from_warehouse", "=", "Dreamwiseagency"]]`
- `limit_page_length`: Maximum records to return (default `100`)
- `limit_start`: Offset for pagination (default `0`)

**Response (200):**
```json
{
  "data": [
    {
      "name": "STE-00015",
      "posting_date": "2026-09-09 00:00:00",
      "from_warehouse": "Dreamwiseagency",
      "to_warehouse": "store 2",
      "total_outgoing_value": 450.0,
      "remarks": "Inter-branch inventory transfer from main depot",
      "docstatus": 1
    }
  ]
}
```

---

### `GET /api/resource/Stock Entry/<name>`
*Retrieves complete details of a specific Stock Entry including line items.*

**Response (200):**
```json
{
  "data": {
    "name": "STE-00015",
    "stock_entry_type": "Material Transfer",
    "posting_date": "2026-09-09 00:00:00",
    "from_warehouse": "Dreamwiseagency",
    "to_warehouse": "store 2",
    "remarks": "Inter-branch inventory transfer from main depot",
    "total_outgoing_value": 450.0,
    "docstatus": 1,
    "items": [
      {
        "item_code": "103",
        "item_name": "Stock 4",
        "qty": 10.0,
        "uom": "Each",
        "s_warehouse": "Dreamwiseagency",
        "t_warehouse": "store 2",
        "basic_rate": 45.0,
        "basic_amount": 450.0
      }
    ]
  }
}
```

---

### `PUT /api/resource/Stock Entry/<name>`
*Cancels a submitted stock entry and rolls back inventory movements.*

**Request:**
```json
{
  "docstatus": 2
}
```

**Response (200):**
```json
{
  "data": {
    "name": "STE-00015",
    "status": "cancelled",
    "docstatus": 2
  }
}
```

---

### `POST /api/resource/Stock Reconciliation`
*Performs physical stock take / inventory adjustment. Compares counted physical quantities against current system valuation, computes variance, creates an audit record, and synchronizes on-hand stock.*

**Request:**
```json
{
  "company": "store 2",
  "posting_date": "2026-09-09 16:30:00",
  "remarks": "Weekly physical stock count",
  "items": [
    {
      "item_code": "103",
      "warehouse": "store 2",
      "qty": 30.0
    }
  ]
}
```

**Response (200):**
```json
{
  "data": {
    "name": "ADJ-00008",
    "company": "store 2",
    "posting_date": "2026-09-09 16:30:00",
    "docstatus": 1
  }
}
```

---

### `GET /api/method/saas_api.www.api.get_stock_reconciliation_with_items`
*Retrieves history of stock reconciliations / adjustments with line items and count differences.*

**Query Parameters:**
- `from_date`: Start date (`YYYY-MM-DD`)
- `to_date`: End date (`YYYY-MM-DD`)
- `cost_center`: Warehouse/Store name

**Response (200):**
```json
{
  "message": [
    {
      "name": "ADJ-00008",
      "posting_date": "2026-09-09 16:30:00",
      "store": "store 2",
      "status": "posted",
      "items": [
        {
          "item_code": "103",
          "item_name": "Stock 4",
          "on_hand": 25.0,
          "counted": 30.0,
          "difference": 5.0
        }
      ]
    }
  ]
}
```

---

### `GET /api/method/saas_api.www.api.get_stock_purchases_with_items`
*Retrieves incoming supplier purchase stock receipts with line item details.*

**Query Parameters:**
- `from_date`: Start date (`YYYY-MM-DD`)
- `to_date`: End date (`YYYY-MM-DD`)
- `supplier`: Optional supplier name filter

**Response (200):**
```json
{
  "message": [
    {
      "name": "PUR-2026-00005",
      "posting_date": "2026-09-08",
      "supplier": "ABC Distributors",
      "store": "store 2",
      "total_amount": 450.00,
      "items": [
        {
          "item_code": "103",
          "item_name": "Stock 4",
          "qty": 10.0,
          "rate": 45.00,
          "amount": 450.00
        }
      ]
    }
  ]
}
```

---

### `GET /api/resource/Warehouse`
*Returns all active stores/warehouses accessible for stock movements and allocation.*

**Alias:** `GET /api/method/havano_pos_integration.api.get_warehouses`

**Response (200):**
```json
{
  "data": [
    {
      "name": "store 2",
      "warehouse_name": "store 2",
      "is_default": true
    },
    {
      "name": "Dreamwiseagency",
      "warehouse_name": "Dreamwiseagency",
      "is_default": false
    }
  ]
}
```
