# -*- coding: utf-8 -*-
# Copyright (c) 2026, Frontier Softech and contributors

import frappe
from frappe import _

from auto_insurance.insurance_v2.api import get_supplier_rows_for_item


def create_insurance_purchase_receipt(doc, method=None):
	"""Sales Invoice before_submit: for each insurance item, create + submit an
	auto Purchase Receipt named after the item's insurance serial number.

	Supplier + supplier_address are read from the SI item row (populated by validate
	or picked by the user for multi-supplier categories). Returns are skipped.
	"""
	if doc.is_return:
		return

	for item in doc.items:
		item_category = frappe.db.get_value("Item", item.item_code, "custom_item_category")
		if not item_category:
			continue

		auto_pr = frappe.db.get_value(
			"Item Category", item_category, "generate_auto_purchase_reciept"
		)
		if not auto_pr:
			continue

		if not item.get("custom_insurance_sr_no"):
			frappe.throw(_("Insurance Serial No is mandatory for item: {0}").format(item.item_name))

		supplier = item.get("custom_insurance_supplier")
		supplier_address = item.get("custom_insurance_supplier_address")

		if not supplier:
			rows = get_supplier_rows_for_item(item.item_code, doc.company)
			if not rows:
				frappe.throw(
					_("Category Supplier not set for Item Category {0} and Company {1}").format(
						item_category, doc.company
					)
				)
			supplier = rows[0]["supplier"]
			supplier_address = supplier_address or rows[0].get("supplier_address")

		if not supplier_address:
			supplier_address = frappe.db.get_value(
				"Item Category Supplier",
				{"parent": item_category, "company": doc.company, "supplier": supplier},
				"supplier_address",
			)

		_create_pr_for_item(doc, item, supplier, supplier_address)


def _create_pr_for_item(sales_invoice, si_item, supplier, supplier_address):
	insurance_sr_no = si_item.custom_insurance_sr_no

	rejected_warehouse = frappe.db.get_value(
		"Warehouse",
		{"is_rejected_warehouse": 1, "company": sales_invoice.company},
		"name",
	)

	address = frappe.db.get_value(
		"Address",
		sales_invoice.company_address,
		["gst_state_number", "gst_state"],
		as_dict=True,
	)
	place_of_supply = f"{address.gst_state_number}-{address.gst_state}" if address else None

	pr = frappe.new_doc("Purchase Receipt")
	pr.company = sales_invoice.company
	pr.place_of_supply = place_of_supply
	pr.supplier = supplier
	pr.supplier_address = supplier_address
	pr.set_posting_time = 1
	pr.posting_date = sales_invoice.posting_date
	pr.posting_time = sales_invoice.posting_time
	pr.branch = sales_invoice.branch
	pr.rejected_warehouse = rejected_warehouse
	pr.custom_invoice_attachment = "/files/auto-pr-placeholder.txt"

	rate = frappe.db.get_value(
		"Item Price",
		{"item_code": si_item.item_code, "price_list": "Standard Buying"},
		"price_list_rate",
	)

	pr.append("items", {
		"item_code": si_item.item_code,
		"item_name": si_item.item_name,
		"description": si_item.description or si_item.item_name,
		"qty": si_item.qty,
		"uom": si_item.uom,
		"stock_uom": si_item.stock_uom,
		"conversion_factor": si_item.conversion_factor or 1,
		"rate": rate,
		"warehouse": si_item.warehouse,
		"branch": si_item.branch,
	})

	pr.run_method("set_missing_values")
	pr.run_method("calculate_taxes_and_totals")

	pr.insert(ignore_permissions=True)

	new_name = _get_unique_pr_name(insurance_sr_no)
	pr.rename(new_name, force=True)

	pr = frappe.get_doc("Purchase Receipt", new_name)
	pr.submit()

	frappe.msgprint(
		_("Purchase Receipt {0} created and submitted for {1}").format(new_name, si_item.item_name),
		alert=True,
		indicator="green",
	)


def _get_unique_pr_name(base_name):
	new_name = base_name
	counter = 1
	while frappe.db.exists("Purchase Receipt", new_name):
		new_name = f"{base_name}-{counter}"
		counter += 1
	return new_name
