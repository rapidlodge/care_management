"""Fail-closed controls for prohibited participant credential storage."""

import re
from collections.abc import Mapping

import frappe
from frappe import _

PROHIBITED_STORAGE_DOCTYPES = frozenset(
	{
		"Participant Profile",
		"Participant Sensitive Identity",
	}
)
PROHIBITED_MYGOV_FIELDNAMES = frozenset(
	{
		"mygov",
		"mygov_account",
		"mygov_id",
		"mygov_login",
		"mygov_username",
		"mygov_password",
		"mygov_passcode",
		"mygov_pin",
		"mygov_token",
		"mygov_secret",
		"mygov_credential",
		"mygov_portal_access",
	}
)
_PROHIBITED_NORMALIZED_NAMES = frozenset(
	re.sub(r"[^a-z0-9]", "", fieldname.lower()) for fieldname in PROHIBITED_MYGOV_FIELDNAMES
)


def _normalized_identifier(value):
	return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def is_prohibited_mygov_identifier(value):
	normalized = _normalized_identifier(value)
	return normalized in _PROHIBITED_NORMALIZED_NAMES or normalized.startswith("mygov")


def _payload_keys(payload):
	if isinstance(payload, Mapping):
		return payload.keys()
	return getattr(payload, "__dict__", {}).keys()


def reject_prohibited_mygov_storage(payload):
	if any(is_prohibited_mygov_identifier(key) for key in _payload_keys(payload)):
		frappe.throw(
			_("Prohibited credential storage is not accepted."),
			frappe.ValidationError,
		)


def validate_prohibited_storage_metadata(doc, method=None):
	if doc.doctype == "Custom Field":
		target_doctype = doc.get("dt")
		identifiers = (doc.get("fieldname"), doc.get("label"))
	elif doc.doctype == "Property Setter":
		target_doctype = doc.get("doc_type")
		identifiers = (doc.get("field_name"),)
		if doc.get("property") in {"fieldname", "label", "options"}:
			identifiers += (doc.get("value"),)
	else:
		return

	if target_doctype not in PROHIBITED_STORAGE_DOCTYPES:
		return
	if any(is_prohibited_mygov_identifier(identifier) for identifier in identifiers):
		frappe.throw(
			_("Prohibited credential storage metadata is not accepted."),
			frappe.ValidationError,
		)
