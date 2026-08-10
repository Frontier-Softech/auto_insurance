# -*- coding: utf-8 -*-
# Copyright (c) 2026, Frontier Softech and contributors

import frappe


def _fetch_supplier_rows(item_category, company):
	if not item_category or not company:
		return []
	return frappe.get_all(
		"Item Category Supplier",
		filters={"parent": item_category, "company": company},
		fields=["supplier", "supplier_address"],
		order_by="idx asc",
	)


def get_supplier_rows_for_item(item_code, company):
	item_category = frappe.db.get_value("Item", item_code, "custom_item_category")
	if not item_category:
		return []
	return _fetch_supplier_rows(item_category, company)


@frappe.whitelist()
def get_category_suppliers(item_code, company):
	"""Return list of {supplier, supplier_address, supplier_name} rows configured on
	the Item's Item Category for the given Company. Consumed by Sales Invoice JS and
	the POS UI to know how many supplier choices exist for the auto Purchase Receipt.
	"""
	rows = get_supplier_rows_for_item(item_code, company)
	for r in rows:
		r["supplier_name"] = frappe.db.get_value("Supplier", r["supplier"], "supplier_name")
	return rows


@frappe.whitelist()
def filter_category_suppliers(doctype, txt, searchfield, start, page_len, filters):
	"""Link field query for `custom_insurance_supplier` on Sales Invoice Item.
	Restricts the supplier dropdown to the rows configured on the item's Item Category
	for the invoice's Company.
	"""
	item_code = (filters or {}).get("item_code")
	company = (filters or {}).get("company")
	rows = get_supplier_rows_for_item(item_code, company)
	suppliers = [r["supplier"] for r in rows if r.get("supplier")]
	if not suppliers:
		return []

	txt_like = f"%{txt or ''}%"
	return frappe.db.sql(
		"""
		SELECT name, supplier_name
		FROM `tabSupplier`
		WHERE name IN %(suppliers)s
		  AND (name LIKE %(txt)s OR supplier_name LIKE %(txt)s)
		ORDER BY name
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"suppliers": tuple(suppliers),
			"txt": txt_like,
			"start": int(start or 0),
			"page_len": int(page_len or 20),
		},
	)
