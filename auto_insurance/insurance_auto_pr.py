# -*- coding: utf-8 -*-
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from pydoc import doc

from pydoc import doc

import frappe
from frappe import _

def create_insurance_purchase_receipt(doc, method=None):
    """Auto create purchase receipt for insurance items before submitting sales invoice.

    Each insurance item with a serial number gets its own Purchase Receipt,
    named after the Insurance Serial No from the item row.
    """
    if doc.is_return:
        for item in doc.items:
            if item.custom_insurance_sr_no:
                # Assuming custom_insurance_sr_no stores Purchase Receipt name
                pr_name = item.custom_insurance_sr_no

                if frappe.db.exists("Purchase Receipt", pr_name):
                    pr_doc = frappe.get_doc("Purchase Receipt", pr_name)

                    if pr_doc.docstatus == 1:  # Submitted
                        pr_doc.cancel()
    else:                        
        items_needing_pr = []

        for item in doc.items:
            # Get item's custom_item_category (Link to Item Category)
            item_category = frappe.db.get_value("Item", item.item_code, "custom_item_category")

            if not item_category:
                continue

            # Check if auto PR is enabled for this item category
            # Note: field name has typo "reciept" in the database
            auto_pr = frappe.db.get_value("Item Category", item_category, "generate_auto_purchase_reciept")

            if not auto_pr:
                continue

            # Get supplier for this item category
            category_supplier = frappe.db.get_value("Item Category", item_category, "category_supplier")

            if not category_supplier:
                frappe.throw(_("Category Supplier not set for Item Category: {0}").format(item_category))

            # Validate insurance serial number exists on the item row
            if not item.custom_insurance_sr_no:
                frappe.throw(_("Insurance Serial No is mandatory for item: {0}").format(item.item_name))

            items_needing_pr.append({
                "item": item,
                "supplier": category_supplier,
                "insurance_sr_no": item.custom_insurance_sr_no
            })

        # If no items need PR, exit
        if not items_needing_pr:
            return

        # Create Purchase Receipt for each insurance item
        for item_data in items_needing_pr:
            create_pr_for_item(doc, item_data)


def create_pr_for_item(sales_invoice, item_data):
    """Create and submit purchase receipt for an insurance item"""

    si_item = item_data["item"]
    supplier = item_data["supplier"]
    insurance_sr_no = item_data["insurance_sr_no"]

    rejected_warehouse = frappe.db.get_value("Warehouse", {"is_rejected_warehouse": 1, "company": sales_invoice.company}, "name")

    # Create new Purchase Receipt
    pr = frappe.new_doc("Purchase Receipt")
    pr.supplier = supplier
    pr.set_posting_time = 1
    pr.posting_date = sales_invoice.posting_date
    pr.posting_time = sales_invoice.posting_time
    pr.branch = sales_invoice.branch
    pr.rejected_warehouse = rejected_warehouse
    # Set dummy invoice attachment (mandatory field) - to be replaced when actual invoice arrives
    pr.custom_invoice_attachment = "/files/auto-pr-placeholder.txt"

    item_price_list = frappe.db.get_value("Item Price", {"item_code" : si_item.item_code, "price_list": "Standard Buying"}, "price_list_rate")

    # Add the item to PR
    pr.append("items", {
        "item_code": si_item.item_code,
        "item_name": si_item.item_name,
        "description": si_item.description or si_item.item_name,
        "qty": si_item.qty,
        "uom": si_item.uom,
        "stock_uom": si_item.stock_uom,
        "conversion_factor": si_item.conversion_factor or 1,
        "rate": item_price_list,
        "warehouse": si_item.warehouse,
        "branch": si_item.branch,
    })

    pr.run_method("set_missing_values")
    pr.run_method("calculate_taxes_and_totals")

    # Insert the PR
    pr.insert(ignore_permissions=True)

    # Rename to insurance serial number
    new_name = get_unique_pr_name(insurance_sr_no)
    pr.rename(new_name, force=True)

    # Reload and submit the PR
    pr = frappe.get_doc("Purchase Receipt", new_name)
    pr.submit()

    frappe.msgprint(
        _("Purchase Receipt {0} created and submitted for {1}").format(new_name, si_item.item_name),
        alert=True,
        indicator="green"
    )


def get_unique_pr_name(base_name):
    """Generate unique PR name based on insurance serial number"""

    new_name = base_name
    counter = 1

    # Make sure name is unique
    while frappe.db.exists("Purchase Receipt", new_name):
        new_name = "{0}-{1}".format(base_name, counter)
        counter += 1

    return new_name

