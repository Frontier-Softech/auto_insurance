# -*- coding: utf-8 -*-
# Copyright (c) 2026, Frontier Softech and contributors

import frappe
from frappe import _

from auto_insurance.insurance_v2.api import get_supplier_rows_for_item


def validate_insurance_supplier(doc, method=None):
	"""On Sales Invoice validate:
	- For every item whose Item Category has `generate_auto_purchase_reciept` = 1:
	  * If category has 0 configured supplier rows for the invoice Company → throw.
	  * If category has exactly 1 row → auto-fill missing supplier/address on the SI item.
	  * If category has 2+ rows → require `custom_insurance_supplier` on the SI item AND
	    ensure the chosen supplier is one of the configured rows (tamper check).
	- Returns / credit notes are skipped (no PR created for returns today).
	"""
	if doc.get("is_return"):
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

		rows = get_supplier_rows_for_item(item.item_code, doc.company)

		if not rows:
			frappe.throw(
				_("Category Supplier not set for Item Category {0} and Company {1}").format(
					item_category, doc.company
				)
			)

		if len(rows) == 1:
			if not item.get("custom_insurance_supplier"):
				item.custom_insurance_supplier = rows[0]["supplier"]
			if not item.get("custom_insurance_supplier_address") and rows[0].get("supplier_address"):
				item.custom_insurance_supplier_address = rows[0]["supplier_address"]
			continue

		if not item.get("custom_insurance_supplier"):
			frappe.throw(
				_("Select Insurance Supplier for item {0} (row {1}). Item Category {2} has multiple suppliers configured for company {3}.").format(
					item.item_name, item.idx, item_category, doc.company
				)
			)

		configured = {r["supplier"] for r in rows}
		if item.custom_insurance_supplier not in configured:
			frappe.throw(
				_("Insurance Supplier {0} on item {1} is not configured on Item Category {2} for company {3}.").format(
					item.custom_insurance_supplier, item.item_name, item_category, doc.company
				)
			)
