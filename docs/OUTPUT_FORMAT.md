# Output format

## CSV layout

The CSV follows the purchase-entry Excel sheet:

| Row | Contents |
|---|---|
| 1 | Header titles. Column A is empty, as in the Excel sheet |
| 2 | Header values |
| 3 | Empty |
| 4 | Item titles |
| 5 … | One row per item, numbered from 1 |
| last | `Total` row with total quantity and total amount (can be turned off) |

```csv
,Date,Supplier Name,Purchase Order Date,Purchase Order Number,L.R Booking Date,Stock Received Date,Invoice Number,Invoice Date,GRN Number
,,Sample Textiles,,,,,ST 900,30-01-2026,

Sl.No,SKU No./Item ID.,Article ID,Brand Name,Design Name,Size,Cup Size,Colour,Quantity,Cost Price,M.R.P,Amount
1,,7001,ACME,CLASSIC TWILL,,,,13.60,675.00,,9180.00
2,,7002,ACME,FLAIR,,,,13.60,799.00,,10866.40
Total,,,,,,,,27.20,,,20046.40
```

- Encoding: UTF-8. The command line and `ScanToFileAsync` add a BOM so Excel shows it correctly.
- Line endings: CRLF (Windows).
- Numbers: no thousands separators, decimals as printed (`1,199.00` → `1199.00`).
- Dates: `dd-mm-yyyy` by default (`date_format` in `settings.yaml`).

## Header columns

| CSV column | JSON key | Where it comes from |
|---|---|---|
| Date | `date` | Empty, or today's date when `fill_date_with_today: true` |
| Supplier Name | `supplier_name` | `name` of the matching profile in `suppliers.yaml`. For unknown suppliers, the largest text at the top of the page |
| Purchase Order Date | `po_date` | Value next to a label such as *PO Date*, *Order Date* |
| Purchase Order Number | `po_number` | Value next to *PO No*, *Order No* |
| L.R Booking Date | `lr_booking_date` | Date next to *LR Date*, *LR No. & Date* |
| Stock Received Date | `stock_received_date` | Always empty. Fill in your application |
| Invoice Number | `invoice_number` | Value next to *Invoice No*, *Bill No*, *Ref No* |
| Invoice Date | `invoice_date` | Value next to *Invoice Date*, *Bill Date*, *Ref Date* |
| GRN Number | `grn_number` | Always empty. Fill in your application |

The label lists are in `settings.yaml` → `header_fields`.

## Item columns

| CSV column | JSON key | Read from table column (first found) |
|---|---|---|
| Sl.No | — | Numbered 1, 2, 3 … in the CSV |
| SKU No./Item ID. | `sku` | Item, Item Code, SKU, Product Code, Style Code |
| Article ID | `article_id` | Article, Art No. Or the last part of a description like `BRAND/DESIGN/ARTICLE` |
| Brand Name | `brand` | Brand column, description pattern, the supplier profile's `brand`, or a *Brand :* label on the invoice |
| Design Name | `design_name` | Design, Product, Style, or the middle part of `BRAND/DESIGN/ARTICLE` |
| Size | `size` | Size |
| Cup Size | `cup_size` | Cup Size, Cup |
| Colour | `colour` | Colour, Color, Shade, or decoded from the SKU's last letters (per supplier) |
| Quantity | `quantity` | First found of: Total Qty, Qty, Quantity, Mtrs, Meters, Pcs, Nos |
| Cost Price | `cost_price` | WS Price, Rate, Cost Price, Price, Unit Price |
| M.R.P | `mrp` | MRP |
| Amount | `amount` | First found of: Total, Total Amt, Total Amount, Net Amount, Amount, Value, Taxable Value |

All of these lists can be changed in `settings.yaml`. See [CONFIGURATION.md](CONFIGURATION.md).

### Default choices

| Question | Default | Change with |
|---|---|---|
| Fabric sold by metre with both *PCS* and *Mtrs* columns: which is the quantity? | **Metres**, because `Rate × Mtrs = Amount` | `output.quantity_priority` |
| Which amount: before GST (*Taxable Value*) or including GST (*Total*)? | **Line total including GST** (*Total*) | `output.amount_priority`: put `taxable value` first |
| Cost price | **WS Price / Rate** as printed (before discount) | `item_columns.cost_price` |

## Warnings

The JSON `warnings` list (and the `X-VBOCR-Warnings` header) reports:

| Warning | Meaning |
|---|---|
| `Page N: item table not found` | No serial-number header (S.No, Sl.No, …) was found on that page |
| `Item N: missing quantity` / `missing amount` | The row was found, but that cell was empty or unreadable |
| `No items found` | Nothing usable on any page |
