# Havano POS Desk Odoo - Product Variants & Attributes API Reference

This reference document outlines the complete lifecycle of **Product Variants** and **Variant Attributes** in Havano POS Desk Odoo: how they work, how to activate them, data models, stock allocation behavior, and comprehensive API endpoints with request and response examples.

---

## 1. Concepts & Architecture

### A. Two Modes of Variants
1. **Manual / Direct Variants**:
   - Direct sub-variants linked to a parent product (`havanoposdesk.product.variant`) with custom names (e.g., `"Standard Edition"`, `"Deluxe Edition"`).
   - Each variant has its own `cost_price`, `selling_price`, and tracked `on_hand_qty`.
2. **Attribute-Driven Variants (Variant Attributes)**:
   - When **Variant Attributes** is turned on for a tenant, businesses can define reusable attributes (e.g., `Size`, `Color`, `Material`, `Shoe Size`) and assign specific attribute values (e.g., `Small`, `Medium`, `Large`, `Red`, `Blue`).
   - The product interface dynamically provides slot dropdowns (Attribute 1–5) and automatically computes composite variant names (e.g., `"Large / Blue"`).

---

## 2. Enabling Variant Attributes

### Option 1: Backoffice Web UI
1. Navigate to **Configurations / Settings** (`/Havano/action-256` or `/Havano/action-324`).
2. Select the **Stock** tab (`havanoposdesk_stock`).
3. Under **Stock Configurations**, toggle on **Variant Attributes**.
4. Click **Save**.

### Option 2: Database / Python ORM
```python
tenant = env['havanoposdesk.tenant'].browse(tenant_id)
tenant.write({'enable_variant_attributes': True})
```

---

## 3. Data Models Reference

### 1. `havanoposdesk.attribute` (Variant Attribute)
| Field | Type | Description |
| :--- | :--- | :--- |
| `name` | Char (Required) | Name of attribute (e.g., `Size`, `Color`, `Material`) |
| `active` | Boolean | Active status toggle (defaults to `True`) |
| `sequence` | Integer | Display order sequence |
| `value_ids` | One2many | Associated values (`havanoposdesk.attribute.value`) |
| `tenant_id` | Many2one | Multi-tenant isolation reference |

### 2. `havanoposdesk.attribute.value` (Attribute Value)
| Field | Type | Description |
| :--- | :--- | :--- |
| `attribute_id` | Many2one | Parent attribute |
| `name` | Char (Required) | Value name (e.g., `Small`, `Medium`, `Large`, `Red`, `Blue`) |
| `sequence` | Integer | Display sequence |
| `tenant_id` | Many2one | Multi-tenant isolation reference |

### 3. `havanoposdesk.product.variant` (Product Variant)
| Field | Type | Description |
| :--- | :--- | :--- |
| `product_id` | Many2one (Required) | Parent product (`havanoposdesk.product`) |
| `name` | Char (Required) | Variant name (e.g., `Large / Blue`) |
| `cost_price` | Float | Variant-specific cost price |
| `selling_price` | Float | Variant-specific selling price |
| `allocate_qty` | Float | Stock qty to allocate from parent unallocated inventory on create/write |
| `on_hand_qty` | Float (Readonly) | Computed on-hand stock across stores |
| `attribute_value_1_id` ... `5_id` | Many2one | Attribute value slots 1 to 5 |
| `attribute_value_ids` | Many2many | All linked attribute values |
| `tenant_id` | Many2one | Multi-tenant isolation reference |

---

## 4. API Endpoints Reference

### Header Authentication
All REST API requests require bearer authentication:
```http
Authorization: Bearer <token>
Content-Type: application/json
```

---

### `GET /api/products/`
*Retrieve all products for the authenticated user/tenant, including variant arrays.*

#### Query Parameters:
* `limit` *(optional, integer)*: Maximum records to return.
* `store_id` *(optional, integer)*: Filter products by store.

#### Response (200 OK):
```json
[
  {
    "id": 103928,
    "name": "Men Casual T-Shirt",
    "item_code": "PROD-00452",
    "barcode": "890123456789",
    "buying_price": 5.0,
    "selling_price": 12.0,
    "track_qty": true,
    "is_bundle": 0,
    "is_stock_item": 1,
    "is_sales_item": 1,
    "sellbyprice": 0,
    "sell_by_price": 0,
    "category": 14,
    "uom": 1,
    "tenant_id": 164,
    "store_id": 2,
    "is_variant": 1,
    "variants": [
      {
        "id": 101,
        "name": "Small / Red",
        "cost_price": 5.0,
        "selling_price": 12.0,
        "on_hand_qty": 20.0
      },
      {
        "id": 102,
        "name": "Medium / Red",
        "cost_price": 5.0,
        "selling_price": 12.0,
        "on_hand_qty": 35.0
      },
      {
        "id": 103,
        "name": "Large / Blue",
        "cost_price": 5.5,
        "selling_price": 14.0,
        "on_hand_qty": 15.0
      }
    ]
  }
]
```

---

### `POST /api/products/`
*Create a new product along with variants and initial stock allocation.*

#### Request Body:
```json
{
  "name": "Men Polo Shirt",
  "item_code": "POLO-001",
  "barcode": "789123456001",
  "buying_price": 6.0,
  "selling_price": 15.0,
  "track_qty": true,
  "category_id": 14,
  "uom_id": 1,
  "store_ids": [2],
  "is_variant": true,
  "variants": [
    {
      "name": "Medium / Black",
      "cost_price": 6.0,
      "selling_price": 15.0,
      "allocate_qty": 10.0
    },
    {
      "name": "Large / Black",
      "cost_price": 6.0,
      "selling_price": 15.0,
      "allocate_qty": 15.0
    }
  ]
}
```

#### Response (201 Created):
```json
{
  "message": "Product created successfully",
  "id": 103929,
  "data": {
    "id": 103929,
    "name": "Men Polo Shirt",
    "item_code": "POLO-001",
    "buying_price": 6.0,
    "selling_price": 15.0,
    "is_variant": 1,
    "variants": [
      {
        "id": 104,
        "name": "Medium / Black",
        "cost_price": 6.0,
        "selling_price": 15.0,
        "on_hand_qty": 10.0
      },
      {
        "id": 105,
        "name": "Large / Black",
        "cost_price": 6.0,
        "selling_price": 15.0,
        "on_hand_qty": 15.0
      }
    ]
  }
}
```

---

### `GET /api/products/<int:product_id>`
*Retrieve details and variant list of a specific product.*

#### Response (200 OK):
```json
{
  "id": 103929,
  "name": "Men Polo Shirt",
  "item_code": "POLO-001",
  "buying_price": 6.0,
  "selling_price": 15.0,
  "is_variant": 1,
  "variants": [
    {
      "id": 104,
      "name": "Medium / Black",
      "cost_price": 6.0,
      "selling_price": 15.0,
      "on_hand_qty": 10.0
    },
    {
      "id": 105,
      "name": "Large / Black",
      "cost_price": 6.0,
      "selling_price": 15.0,
      "on_hand_qty": 15.0
    }
  ]
}
```

---

### `PUT /api/products/<int:product_id>`
*Update an existing product and add or modify variants.*

#### Request Body:
```json
{
  "selling_price": 16.50,
  "variants": [
    {
      "name": "XL / Black",
      "cost_price": 7.0,
      "selling_price": 17.50,
      "allocate_qty": 5.0
    }
  ]
}
```

#### Response (200 OK):
```json
{
  "message": "Product updated successfully",
  "id": 103929,
  "data": {
    "id": 103929,
    "name": "Men Polo Shirt",
    "selling_price": 16.50,
    "is_variant": 1,
    "variants": [
      {
        "id": 104,
        "name": "Medium / Black",
        "cost_price": 6.0,
        "selling_price": 15.0,
        "on_hand_qty": 10.0
      },
      {
        "id": 105,
        "name": "Large / Black",
        "cost_price": 6.0,
        "selling_price": 15.0,
        "on_hand_qty": 15.0
      },
      {
        "id": 106,
        "name": "XL / Black",
        "cost_price": 7.0,
        "selling_price": 17.50,
        "on_hand_qty": 5.0
      }
    ]
  }
}
```

---

### `GET /api/method/havano_pos_integration.api.get_products` (POS Terminal Sync)
*Used by POS terminals to sync catalog items, including pricing, warehouse stock, and active variant attributes.*

#### Request:
`GET /api/method/havano_pos_integration.api.get_products?shop_id=2&page=1&limit=500`

#### Response (200 OK):
```json
{
  "message": {
    "products": [
      {
        "itemcode": "POLO-001",
        "itemname": "Men Polo Shirt",
        "groupname": "Apparel",
        "maintainstock": 1,
        "is_bundle": 0,
        "is_stock_item": 1,
        "is_sales_item": 1,
        "sellbyprice": 0,
        "sell_by_price": 0,
        "simple_code": null,
        "uom": {
          "stock_uom": "Each",
          "conversions": [
            { "uom": "Each", "conversion_factor": 1.0 }
          ]
        },
        "prices": [
          {
            "priceName": "Standard Selling",
            "price": 16.50,
            "uom": "Each",
            "type": "selling",
            "store": null,
            "warehouse": null,
            "qty_to_be_sold": 1.0,
            "qtyOnHand": 30.0
          }
        ],
        "warehouses": [
          {
            "warehouse": "Main Store",
            "qtyOnHand": 30.0
          }
        ],
        "taxes": [],
        "variant_attributes": {
          "Size": {
            "id": 12,
            "value": "Large",
            "attribute_id": 3,
            "status": true
          },
          "Color": {
            "id": 18,
            "value": "Black",
            "attribute_id": 4,
            "status": true
          }
        }
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 500,
      "total_count": 1,
      "total_pages": 1,
      "has_next_page": false,
      "has_prev_page": false
    }
  }
}
```

---

### `POST /saas_api/make_sale` (POS Variant Sale Invoice)
*Submitting sales containing product variants.*

#### Request Body:
```json
{
  "pos_invoice": {
    "pos_profile": "Terminal 1",
    "store_id": 2,
    "customer": "Walk-in Customer",
    "grand_total": 17.50,
    "paid_amount": 20.00,
    "change_amount": 2.50,
    "items": [
      {
        "item_code": "POLO-001",
        "item_name": "Men Polo Shirt",
        "variant_id": 106,
        "variant_name": "XL / Black",
        "qty": 1.0,
        "rate": 17.50,
        "amount": 17.50,
        "uom": "Each"
      }
    ],
    "payments": [
      {
        "mode_of_payment": "Cash",
        "amount": 20.00
      }
    ]
  }
}
```

#### Response (200 OK):
```json
{
  "message": {
    "status": "success",
    "invoice_id": 5012,
    "invoice_no": "INV/2026/00451",
    "grand_total": 17.50
  }
}
```

---

## 5. Stock Allocation Mechanism

When a variant is created or allocated stock via `allocate_qty`:
1. The system locates base inventory from `havanoposdesk.stock.valuation` where `product_id = parent_id` and `variant_id = False`.
2. It deducts `allocate_qty` from the unallocated stock pool.
3. It credits the variant's valuation record (`variant_id = current_variant_id`).
4. Two ledger audit entries are logged in `havanoposdesk.stock.ledger`:
   - Outflow on parent: `type = 'Variant Allocation Out'`.
   - Inflow on variant: `type = 'Variant Allocation In'`.
