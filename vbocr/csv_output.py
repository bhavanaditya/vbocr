"""Write an Invoice in the purchase-entry CSV layout.

Layout (same as the Excel template):

    row 1   , Date, Supplier Name, Purchase Order Date, ... , GRN Number
    row 2   , <values>
    row 3   (blank)
    row 4   Sl.No, SKU No./Item ID., Article ID, ... , Amount
    row 5+  1, <item values>
    last    Total, , , ... , <total quantity>, , , <total amount>
"""

import csv
import io

from .models import HEADER_FIELDS, ITEM_FIELDS, Invoice
from .text_utils import to_float

HEADER_TITLES = [
    "Date",
    "Supplier Name",
    "Purchase Order Date",
    "Purchase Order Number",
    "L.R Booking Date",
    "Stock Received Date",
    "Invoice Number",
    "Invoice Date",
    "GRN Number",
]

ITEM_TITLES = [
    "Sl.No",
    "SKU No./Item ID.",
    "Article ID",
    "Brand Name",
    "Design Name",
    "Size",
    "Cup Size",
    "Colour",
    "Quantity",
    "Cost Price",
    "M.R.P",
    "Amount",
]


def invoice_to_csv(invoice: Invoice, include_total_row: bool = True) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")

    writer.writerow([""] + HEADER_TITLES)
    writer.writerow([""] + [invoice.header.get(k, "") for k in HEADER_FIELDS])
    writer.writerow([])
    writer.writerow(ITEM_TITLES)
    for number, item in enumerate(invoice.items, start=1):
        writer.writerow([number] + [item.get(k, "") for k in ITEM_FIELDS])

    if include_total_row:
        writer.writerow(
            ["Total"]
            + [""] * (ITEM_FIELDS.index("quantity"))
            + [_total(invoice, "quantity")]
            + [""] * (ITEM_FIELDS.index("amount") - ITEM_FIELDS.index("quantity") - 1)
            + [_total(invoice, "amount")]
        )
    return buffer.getvalue()


def _total(invoice: Invoice, field: str) -> str:
    values = [item.get(field, "") for item in invoice.items]
    total = sum(to_float(v) for v in values)
    if any("." in v for v in values):
        return "{:.2f}".format(total)
    return str(int(round(total)))
