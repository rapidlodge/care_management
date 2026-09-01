# Copyright (c) 2026, Care Management and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe
from decimal import Decimal, InvalidOperation

from frappe.utils import get_datetime, getdate, to_timedelta


WEEKDAY_FIELDS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

REQUIRED_ACTIVE_ITEM_FIELDS = ("medication_name", "route", "prescribed_dose", "dose_unit", "scheduled_time", "indication")

PROTECTED_HISTORY_FIELDS = (
	"medication_name",
	"dosage",
	"route",
	"time_slot",
	"medication_form",
	"strength",
	"prescribed_dose",
	"dose_unit",
	"scheduled_time",
	"frequency",
	"indication",
	"is_prn",
	"is_controlled_drug",
	"is_active",
	"prn_indication",
	"prn_minimum_interval_hours",
	"prn_maximum_dose",
	"prn_review_due_minutes",
	*WEEKDAY_FIELDS,
	"instructions",
	"storage_instructions",
	"side_effects",
	"escalation_instructions",
)


def validate_active_medication_plan_item(row):
	for fieldname in REQUIRED_ACTIVE_ITEM_FIELDS:
		if not row.get(fieldname):
			frappe.throw("Active medication items require complete safe-use information.", frappe.ValidationError)
	if row.get("is_prn"):
		_validate_prn_controls(row)
	if row.route == "Other":
		frappe.throw("Other medication route requires an explicit supported competency mapping.", frappe.ValidationError)
	if row.frequency == "Selected Days" and not any(row.get(day) for day in WEEKDAY_FIELDS):
		frappe.throw("Selected-day medication items require at least one selected weekday.", frappe.ValidationError)
	if row.frequency not in {"Daily", "Selected Days"}:
		frappe.throw("Unknown medication frequency is not safe to activate.", frappe.ValidationError)


def _positive_decimal(value, message):
	try:
		amount = Decimal(str(value))
	except (InvalidOperation, TypeError, ValueError):
		frappe.throw(message, frappe.ValidationError)
	if amount <= 0:
		frappe.throw(message, frappe.ValidationError)
	return amount


def _validate_prn_controls(row):
	if not row.get("prn_indication"):
		frappe.throw("PRN medication requires an indication.", frappe.ValidationError)
	if not row.get("prn_minimum_interval_hours") or int(row.get("prn_minimum_interval_hours") or 0) <= 0:
		frappe.throw("PRN medication requires a positive minimum interval.", frappe.ValidationError)
	_positive_decimal(row.get("prn_maximum_dose"), "PRN medication requires a positive maximum dose.")
	if not row.get("prn_review_due_minutes") or int(row.get("prn_review_due_minutes") or 0) <= 0:
		frappe.throw("PRN medication requires a positive effectiveness review due time.", frappe.ValidationError)


def competency_types_for_plan_item(row):
	requirements = ["General Medication"]
	if row.get("is_prn"):
		requirements.append("PRN Medication")
	if row.get("is_controlled_drug"):
		requirements.append("Controlled Medication")
	if row.route == "Topical":
		requirements.append("Topical Medication")
	elif row.route == "Injection":
		requirements.append("Injection")
	elif row.route == "Inhaled":
		requirements.append("Inhaled Medication")
	elif row.route == "Other":
		frappe.throw("Other medication route requires an explicit supported competency mapping.", frappe.ValidationError)
	return tuple(requirements)


def validate_active_medication_plan_items(rows):
	active_items = [row for row in rows if row.get("is_active", 1)]
	if not active_items:
		frappe.throw("Active medication plans require at least one active medication item.", frappe.ValidationError)
	for row in active_items:
		validate_active_medication_plan_item(row)


def _fieldtype_for(fieldname):
	meta = frappe.get_meta("Medication Plan Item")
	field = meta.get_field(fieldname)
	return field.fieldtype if field else None


def _canonical_history_value(fieldname, value):
	if value in (None, ""):
		return None
	fieldtype = _fieldtype_for(fieldname)
	try:
		if fieldtype == "Date":
			return getdate(value)
		if fieldtype == "Datetime":
			return get_datetime(value)
		if fieldtype == "Time":
			return to_timedelta(value)
		if fieldtype in {"Check", "Int"}:
			return int(value)
	except Exception:
		return object()
	return value


def history_values_match(fieldname, left, right):
	return _canonical_history_value(fieldname, left) == _canonical_history_value(fieldname, right)


class MedicationPlanItem(Document):
	def validate(self):
		self._validate_material_history_unchanged()
		self._validate_parent_movement_boundary()
		self._validate_affected_active_plan_collections()

	def on_trash(self):
		if (
			frappe.db.table_exists("Medication Administration Event")
			and frappe.db.exists("Medication Administration Event", {"medication_plan_item": self.name})
		):
			frappe.throw("Referenced medication plan items cannot be removed or replaced.", frappe.ValidationError)
		self._validate_direct_active_item_delete()

	def _validate_material_history_unchanged(self):
		if self.is_new() or not frappe.db.table_exists("Medication Administration Event"):
			return
		if not frappe.db.exists("Medication Administration Event", {"medication_plan_item": self.name}):
			return
		old = frappe.get_doc("Medication Plan Item", self.name)
		for fieldname in ("parent", "parenttype", "parentfield"):
			if old.get(fieldname) != self.get(fieldname):
				frappe.throw("Referenced medication plan items cannot be reparented.", frappe.ValidationError)
		for fieldname in PROTECTED_HISTORY_FIELDS:
			if not history_values_match(fieldname, old.get(fieldname), self.get(fieldname)):
				frappe.throw("Referenced medication plan items cannot be materially changed.", frappe.ValidationError)

	def _validate_affected_active_plan_collections(self):
		affected_parents = set()
		old = None
		if not self.is_new() and frappe.db.exists("Medication Plan Item", self.name):
			old = frappe.get_doc("Medication Plan Item", self.name)
			if _belongs_to_medication_plan(old):
				affected_parents.add(old.parent)
		if _belongs_to_medication_plan(self):
			affected_parents.add(self.parent)
		for parent in affected_parents:
			_validate_active_plan_collection(parent, self)

	def _validate_parent_movement_boundary(self):
		if self.is_new() or not frappe.db.exists("Medication Plan Item", self.name):
			return
		old = frappe.get_doc("Medication Plan Item", self.name)
		if not _belongs_to_medication_plan(old):
			return
		if old.parent == self.parent and old.parenttype == self.parenttype and old.parentfield == self.parentfield:
			return
		if not _belongs_to_medication_plan(self):
			frappe.throw("Medication plan items cannot be detached from a medication plan.", frappe.ValidationError)
		if not frappe.db.exists("Medication Administration Log", self.parent):
			frappe.throw("Medication plan items can only be moved into a stored medication plan.", frappe.ValidationError)
		source_participant = frappe.db.get_value("Medication Administration Log", old.parent, "participant")
		destination_participant = frappe.db.get_value("Medication Administration Log", self.parent, "participant")
		if source_participant != destination_participant:
			frappe.throw("Medication plan items cannot move across participants.", frappe.ValidationError)

	def _validate_direct_active_item_delete(self):
		if not self.parent or self.parenttype != "Medication Administration Log":
			return
		if not frappe.db.exists("Medication Administration Log", self.parent):
			return
		plan_status = frappe.db.get_value("Medication Administration Log", self.parent, "plan_status")
		if plan_status != "Active" or not self.get("is_active", 1):
			return
		_validate_active_plan_collection(self.parent, removed_item=self)


def _belongs_to_medication_plan(row):
	return (
		row.get("parent")
		and row.get("parenttype") == "Medication Administration Log"
		and row.get("parentfield") == "medication_items"
	)


def _active_plan_status(parent):
	if not parent or not frappe.db.exists("Medication Administration Log", parent):
		return None
	return frappe.db.get_value("Medication Administration Log", parent, "plan_status")


def _stored_plan_items(parent, excluded_name=None):
	fields = sorted({"name", *PROTECTED_HISTORY_FIELDS})
	rows = frappe.get_all(
		"Medication Plan Item",
		filters={
			"parent": parent,
			"parenttype": "Medication Administration Log",
			"parentfield": "medication_items",
		},
		fields=fields,
		order_by="idx asc, name asc",
	)
	return [frappe._dict(row) for row in rows if row.name != excluded_name]


def _validate_active_plan_collection(parent, current_item=None, removed_item=None):
	if _active_plan_status(parent) != "Active":
		return
	excluded_name = current_item.name if current_item and current_item.name else None
	if removed_item and removed_item.name:
		excluded_name = removed_item.name
	rows = _stored_plan_items(parent, excluded_name=excluded_name)
	if current_item and _belongs_to_medication_plan(current_item) and current_item.parent == parent:
		rows.append(current_item)
	validate_active_medication_plan_items(rows)
