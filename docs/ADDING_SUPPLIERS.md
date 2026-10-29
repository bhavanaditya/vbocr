# Adding a supplier

**Most new suppliers work without any change.** VB OCR finds the item table by its serial-number
column, whatever the layout. A supplier profile is only needed to:

- write the supplier's name exactly as you want it in the CSV
- use a header label or table column name that the default lists don't include
- set a default brand
- decode colour codes from SKUs
- split item descriptions in a special way

## Step 1: scan a sample and look at the result

```bat
cd C:\vbocr
.venv\Scripts\python.exe -m vbocr scan C:\Invoices\new-supplier.jpg --json
```

Check:

- **`items` is empty / "item table not found"** → the serial-number header has an unusual name.
  Add it to `item_columns.serial` (go to step 3).
- **A column is empty** → its header name is not in the list. Add it to `item_columns`.
- **A header value is empty** → add the label to `header_fields`.
- **The supplier name is wrong** → add a profile with `name` and `match`.

## Step 2: find text that identifies the supplier

Choose something printed on every invoice from this supplier and **on no other invoice**:
their GSTIN, e-mail address or website. Avoid your own company's name or GSTIN, which
appear on every invoice you receive.

## Step 3: add the profile

Open `config\suppliers.yaml` and add an entry under `suppliers:`:

```yaml
suppliers:
  # ... existing suppliers ...

  - name: Lakshmi Garments                 # written to "Supplier Name"
    match: ["33ABCDE1234F1Z5", "lakshmigarments.com"]
    brand: Lakshmi                          # default "Brand Name" for every item
    header_fields:
      invoice_number: ["bill ref"]          # "Bill Ref : LG-0042"
      po_date: ["date"]                     # a plain "Date" under the PO number
    item_columns:
      serial: ["line"]                      # table numbered under "Line"
      sku: ["style no"]
    colour_from_sku_suffix: 3               # last 3 letters of SKU = colour code
    description_patterns:
      - '^(?P<design_name>.+?)\s+(?P<size>XS|S|M|L|XL|XXL)$'
```

All fields except `name` and `match` are optional. Labels and column names in a profile are
tried **before** the defaults from `settings.yaml`.

To choose quantity or amount columns, use `output.quantity_priority` / `output.amount_priority`
in `settings.yaml`. Those apply to all suppliers.

## Step 4: restart and test

Restart the server (close the window and run `start-server.bat` again), then scan the sample again.

## Examples included

`config\suppliers.yaml` contains two working examples:

| Profile | Shows |
|---|---|
| Garment supplier with SKU codes such as `NTY03140125MST` | `brand`, `colour_from_sku_suffix`, and a plain `Date` label as PO date |
| Fabric wholesaler with descriptions such as `RAYMOND/CLASSIQUE/1315177` | Only `name` and `match`. The default `description_patterns` split brand / design / article |

## What is not supported

- **Handwritten invoices.** Printed text only.
- **Tables without a serial-number column.** Ask the supplier, or add the column name used for
  row numbers to `item_columns.serial`.
- **Items whose details are spread over several separate lines with different layouts per row.**
  Wrapped text in one cell is fine.
