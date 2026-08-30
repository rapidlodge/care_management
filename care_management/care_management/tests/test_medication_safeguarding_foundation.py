import json
import re
from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from care_management.care_management import permissions
from care_management.care_management.doctype.medication_plan_item.medication_plan_item import PROTECTED_HISTORY_FIELDS


RUN_PREFIX = f"R3C1-{frappe.generate_hash(length=8)}"


def _slug(value):
	return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def _today_at(hour):
	return f"{nowdate()} {hour:02d}:00:00"


def _weekday_field(date_value):
	return ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[
		frappe.utils.getdate(date_value).weekday()
	]


def _ensure_master(doctype, fieldname, value):
	existing = frappe.db.get_value(doctype, {fieldname: value}, "name")
	if existing:
		return existing
	return frappe.get_doc({"doctype": doctype, fieldname: value}).insert(ignore_permissions=True).name


def _participant(label, medicare):
	prefix = f"{RUN_PREFIX}-{frappe.generate_hash(length=8)}"
	living = _ensure_master("Living Arrangement", "arrangement_name", f"{prefix} Living {label}")
	consent = _ensure_master("Consent Type", "consent_name", f"{prefix} Consent {label}")
	secondary = _ensure_master("Secondary Disability Type", "disability_name", f"{prefix} Disability {label}")
	return frappe.get_doc(
		{
			"doctype": "Participant Profile",
			"participant": f"{prefix} Participant {label}",
			"legally_competent": "Yes",
			"marital_status": "Single",
			"living_arrangements": [{"living_arrangement": living}],
			"religious_or_spiritual": "No",
			"religion": "No Religion",
			"cald": "No",
			"atsi": "Neither",
			"consent_received": [{"consent_type": consent}],
			"organ_cadaver_donor": "Unknown",
			"chap": "No",
			"peep": "No",
			"risk_or_alert_present": "No",
			"risk_or_alert": "Other",
			"interpreter_required": "No",
			"english_ability": "Fluent",
			"communication_supports_required": "No",
			"communication_type": "Verbal",
			"primary_disability": "Other",
			"secondary_disability": [{"secondary_disability": secondary}],
			"disability_limitations": "Mild",
			"ability_to_act_in_emergency": "Yes",
			"end_of_life_plan": "No",
			"bsp_plan": "No",
			"receive_mobility_allowance": "No",
			"medicare_number": medicare,
			"crn_number": f"{prefix}-{label}-CRN",
			"private_health_care_cover": "No",
			"companion_card": "No",
			"funding_type": "Private",
			"ndia_funding_type": "Plan Managed",
			"pharmacist_name": f"{prefix} Pharmacist",
			"asthma_action_plan": "N/A",
			"ascia_action_plans": "N/A",
		}
	).insert(ignore_permissions=True).name


def _user(label, roles):
	email = f"{RUN_PREFIX.lower()}-{frappe.generate_hash(length=8)}-{_slug(label)}@example.test"
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": f"{RUN_PREFIX} {label}",
			"enabled": 1,
			"user_type": "System User",
			"send_welcome_email": 0,
			"roles": [{"role": role} for role in roles],
		}
	).insert(ignore_permissions=True)
	frappe.clear_cache(user=user.name)
	return user.name


def _grant(user, participant, applicable_for=None):
	return frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": "Participant Profile",
			"for_value": participant,
			"applicable_for": applicable_for,
			"apply_to_all_doctypes": 0 if applicable_for else 1,
		}
	).insert(ignore_permissions=True).name


def _ensure_grant(user, participant, applicable_for=None):
	filters = {
		"user": user,
		"allow": "Participant Profile",
		"for_value": participant,
		"applicable_for": applicable_for,
	}
	if frappe.db.exists("User Permission", filters):
		return None
	return _grant(user, participant, applicable_for=applicable_for)


def _incident(participant, label):
	return frappe.get_doc(
		{
			"doctype": "Incident",
			"participant": participant,
			"assigned_staff": "Administrator",
			"reported_by": "Administrator",
			"reported_on": now_datetime(),
			"time_of_incident": "08:00:00",
			"date_of_incident": nowdate(),
			"location_of_incident": f"{RUN_PREFIX} Location {label}",
			"incident_type": "Medication Error",
			"was_rp_used": "No",
			"full_description_of_incident": f"{RUN_PREFIX} synthetic medication incident {label}",
			"severity": "Low",
		}
	).insert(ignore_permissions=True).name


class TestMedicationSafeguardingFoundation(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.participant_a = _participant("A", "4234567890")
		self.participant_b = _participant("B", "5234567890")
		self.system_manager = _user("System Manager", ["System Manager"])
		self.care_manager = _user("Care Manager", ["Care Manager"])
		self.mixed_manager = _user("Mixed Manager", ["System Manager", "Care Manager"])
		self.care_worker = _user("Care Worker", ["Care Manager", "Support Worker"])
		self.worker = _user("Worker A", ["Support Worker"])
		self.worker_b = _user("Worker B", ["Support Worker"])
		self.role_only_worker = _user("Role Only", ["Support Worker"])
		for user in (self.care_manager, self.care_worker, self.worker):
			_grant(user, self.participant_a)
		_grant(self.worker_b, self.participant_b)
		self.support_plan = self._support_plan(self.participant_a, "A")
		self.support_plan_b = self._support_plan(self.participant_b, "B")
		self.task = self._support_task(self.support_plan, "A", self.worker)
		self.task_b = self._support_task(self.support_plan_b, "B", self.worker_b)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def _support_plan(self, participant, label):
		return frappe.get_doc(
			{
				"doctype": "Support Plan",
				"participant": participant,
				"plan_name": f"{RUN_PREFIX} Support Plan {label}",
				"status": "Active",
				"start_date": nowdate(),
			}
		).insert(ignore_permissions=True).name

	def _support_task(self, support_plan, label, worker=None, source_doc=None, source_row_id=None):
		doc = frappe.get_doc(
			{
				"doctype": "Support Task",
				"support_plan": support_plan,
				"task_name": f"{RUN_PREFIX} Medication Task {label}",
				"task_category": "Medication",
				"status": "Active",
				"clinical_priority": "Mandatory",
				"staff_count_required": 1,
				"schedule_rules": [
					{
						"scheduled_time": "08:00:00",
						"recurrence_type": "Daily",
						"start_date": nowdate(),
						"is_floating": 0,
					}
				],
				"source_doctype": source_doc.doctype if source_doc else None,
				"source_docname": source_doc.name if source_doc else None,
				"source_row_id": source_row_id,
			}
		).insert(ignore_permissions=True)
		if worker:
			doc.append("assigned_staff_table", {"staff_user": worker, "role": "Primary Carer"})
			doc.save(ignore_permissions=True)
		return doc.name

	def _active_plan(self, participant=None, label="A", effective_from=None, effective_to=None):
		participant = participant or self.participant_a
		effective_from = effective_from or nowdate()
		doc = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": participant,
				"week_commencing": effective_from,
				"plan_status": "Draft",
				"plan_version": 1,
				"effective_from": effective_from,
				"effective_to": effective_to,
				"review_date": add_days(effective_from, 30),
				"approved_by": self.care_manager,
				"approved_on": now_datetime(),
				"purpose_evidence_status": "Recorded",
				"change_reason": f"{RUN_PREFIX} activation {label}",
				"medication_items": [self._item_payload(label)],
			}
		).insert(ignore_permissions=True)
		doc.plan_status = "Active"
		doc.save(ignore_permissions=True)
		return doc

	def _draft_plan(
		self,
		participant=None,
		label="Draft",
		effective_from=None,
		previous_plan=None,
		plan_version=1,
		replacement_plan=None,
	):
		participant = participant or self.participant_a
		effective_from = effective_from or nowdate()
		return frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": participant,
				"week_commencing": effective_from,
				"plan_status": "Draft",
				"plan_version": plan_version,
				"effective_from": effective_from,
				"review_date": add_days(effective_from, 30),
				"previous_plan": previous_plan,
				"replacement_plan": replacement_plan,
				"purpose_evidence_status": "Recorded",
				"change_reason": f"{RUN_PREFIX} draft {label}",
				"medication_items": [self._item_payload(label)],
			}
		).insert(ignore_permissions=True)

	def _item_payload(self, label="A"):
		return {
			"medication_name": f"{RUN_PREFIX} Medication {label}",
			"dosage": "10 mg",
			"route": "Oral",
			"time_slot": "8 AM",
			"medication_form": "Tablet",
			"strength": "10 mg",
			"prescribed_dose": "10",
			"dose_unit": "mg",
			"scheduled_time": "08:00:00",
			"frequency": "Daily",
			"indication": "Routine support",
			"is_active": 1,
		}

	def _selected_days_plan_with_event(self, label="Selected", scheduled_date=None):
		scheduled_date = scheduled_date or add_days(nowdate(), 1)
		selected_weekday = _weekday_field(scheduled_date)
		alternate_weekday = "monday" if selected_weekday != "monday" else "tuesday"
		item = self._item_payload(label)
		item.update({"frequency": "Selected Days", selected_weekday: 1, alternate_weekday: 1})
		plan = self._draft_plan(
			label=label,
			effective_from=scheduled_date,
		)
		plan.set("medication_items", [item])
		plan.save(ignore_permissions=True)
		plan.plan_status = "Active"
		plan.save(ignore_permissions=True)
		self._competency(valid_from=add_days(scheduled_date, -1), expiry_date=add_days(scheduled_date, 30))
		event = self._event(plan=plan, scheduled_datetime=f"{scheduled_date} 08:00:00").insert(ignore_permissions=True)
		with self._as_user(self.worker):
			event.submit()
		plan.reload()
		return plan, event, selected_weekday, alternate_weekday

	def _competency(self, worker=None, status="Active", expiry_date=None, valid_from=None):
		return frappe.get_doc(
			{
				"doctype": "Medication Competency",
				"worker": worker or self.worker,
				"competency_type": "General Medication",
				"status": status,
				"valid_from": valid_from or add_days(nowdate(), -1),
				"expiry_date": expiry_date or add_days(nowdate(), 30),
				"assessed_by": self.care_manager,
				"assessed_on": nowdate(),
			}
		).insert(ignore_permissions=True)

	def _inactive_competency(self, worker, scheduled_date):
		comp = self._competency(
			worker,
			status="Active",
			valid_from=add_days(scheduled_date, -1),
			expiry_date=add_days(scheduled_date, 10),
		)
		comp.is_active = 0
		comp.save(ignore_permissions=True)
		return comp

	def _event(self, plan=None, worker=None, task=None, scheduled_datetime=None, outcome="Administered"):
		plan = plan or self._active_plan()
		item = plan.medication_items[0]
		return frappe.get_doc(
			{
				"doctype": "Medication Administration Event",
				"participant": plan.participant,
				"medication_plan": plan.name,
				"medication_plan_item": item.name,
				"support_task": task,
				"scheduled_datetime": scheduled_datetime or _today_at(8),
				"actual_datetime": scheduled_datetime or _today_at(8),
				"worker": worker or self.worker,
				"prescribed_dose": item.prescribed_dose,
				"administered_dose": item.prescribed_dose,
				"dose_unit": item.dose_unit,
				"route": item.route,
				"outcome": outcome,
			}
		)

	def _medication_task(self, plan, worker=None, label="Medication"):
		return self._support_task(
			self.support_plan if plan.participant == self.participant_a else self.support_plan_b,
			label,
			worker or self.worker,
			source_doc=plan,
			source_row_id=plan.medication_items[0].name,
		)

	def _execution_instance(self, task, scheduled_date=None, scheduled_time="08:00:00", status="Pending"):
		return frappe.get_doc(
			{
				"doctype": "Support Task Execution Instance",
				"support_task": task,
				"scheduled_date": scheduled_date or nowdate(),
				"scheduled_time": scheduled_time,
				"status": status,
			}
		).insert(ignore_permissions=True).name

	def _active_plan_with_two_items(self, label, effective_from=None):
		plan = self._active_plan(label=label, effective_from=effective_from)
		plan.append("medication_items", self._item_payload(f"{label} Second"))
		plan.save(ignore_permissions=True)
		plan.reload()
		self.assertEqual(len([row for row in plan.medication_items if row.get("is_active", 1)]), 2)
		return plan

	def _assert_locked_field_denied(self, plan, fieldname, value):
		plan.reload()
		original = plan.get(fieldname)
		plan.set(fieldname, value)
		with self.subTest(status=plan.plan_status, fieldname=fieldname), self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)
		plan.reload()
		self.assertEqual(plan.get(fieldname), original)

	@contextmanager
	def _as_user(self, user):
		current = frappe.session.user
		frappe.set_user(user)
		try:
			yield
		finally:
			frappe.set_user(current)

	def test_r3_t001_plan_metadata_is_additive_and_legacy_fields_remain(self):
		meta = frappe.get_meta("Medication Administration Log")
		for fieldname in ("participant", "week_commencing", "medication_items", "plan_status", "plan_version"):
			self.assertTrue(meta.has_field(fieldname), f"R3-T001 missing {fieldname}")

	def test_r3_t002_event_links_participant_plan_item_and_task_context(self):
		meta = frappe.get_meta("Medication Administration Event")
		for fieldname in (
			"participant",
			"medication_plan",
			"medication_plan_item",
			"support_task",
			"finalized_by",
			"finalized_on",
			"administrative_override_reason",
			"occurrence_key",
		):
			self.assertTrue(meta.has_field(fieldname), f"R3-T002 missing {fieldname}")

	def test_r3_t003_plan_save_does_not_fabricate_events(self):
		before = frappe.db.count("Medication Administration Event")
		self._active_plan()
		self.assertEqual(frappe.db.count("Medication Administration Event"), before)

	def test_r3_t004_cross_participant_event_plan_task_and_competency_access_denied(self):
		plan = self._active_plan()
		self._competency(self.worker_b)
		event = self._event(plan=plan, worker=self.worker_b, task=self.task_b)
		with self._as_user(self.worker_b), self.assertRaises(frappe.PermissionError):
			event.insert()
		self._competency()
		cross_incident = _incident(self.participant_b, "Cross")
		event = self._event(plan=plan, task=None)
		event.incident = cross_incident
		with self.assertRaises(frappe.PermissionError):
			event.insert(ignore_permissions=True)
		source_plan = self._active_plan(participant=self.participant_b, label="Correction Source")
		source_event = self._event(plan=source_plan, worker=self.worker_b, task=None).insert(ignore_permissions=True)
		event = self._event(plan=plan, task=None)
		event.correction_source = source_event.name
		event.correction_reason = "synthetic correction"
		with self.assertRaises(frappe.ValidationError):
			event.insert(ignore_permissions=True)

	def test_r3_t005_locked_plan_lifecycle_transitions_are_allowed(self):
		plan = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_a,
				"week_commencing": nowdate(),
				"plan_status": "Needs Review",
				"medication_items": [self._item_payload("Lifecycle")],
			}
		).insert(ignore_permissions=True)
		plan.plan_status = "Draft"
		plan.save(ignore_permissions=True)
		plan.approved_by = self.care_manager
		plan.approved_on = now_datetime()
		plan.effective_from = nowdate()
		plan.review_date = add_days(nowdate(), 30)
		plan.purpose_evidence_status = "Recorded"
		plan.change_reason = f"{RUN_PREFIX} lifecycle"
		plan.plan_status = "Active"
		with self._as_user(self.care_manager):
			plan.save()
		self.assertEqual(plan.plan_status, "Active")
		self.assertEqual(plan.approved_by, self.care_manager)
		self.assertTrue(plan.approved_on)
		link_target = self._draft_plan(label="Caller Link Target", effective_from=add_days(nowdate(), 1))
		with self.assertRaisesRegex(frappe.ValidationError, "replacement relationship"):
			self._draft_plan(
				label="Forged New Replacement",
				effective_from=add_days(nowdate(), 2),
				replacement_plan=link_target.name,
			)
		stored_draft = self._draft_plan(label="Stored Draft", effective_from=add_days(nowdate(), 3))
		stored_draft.replacement_plan = link_target.name
		with self.assertRaisesRegex(frappe.ValidationError, "replacement relationship"):
			stored_draft.save(ignore_permissions=True)
		stored_draft.reload()
		self.assertFalse(stored_draft.replacement_plan)
		plan.plan_status = "Superseded"
		plan.replacement_plan = link_target.name
		with self.assertRaisesRegex(frappe.ValidationError, "superseded by an approved replacement"):
			plan.save(ignore_permissions=True)
		plan.reload()
		self.assertEqual(plan.plan_status, "Active")
		self.assertFalse(plan.replacement_plan)
		plan.flags.authoritative_replacement_supersession = True
		plan.plan_status = "Superseded"
		plan.replacement_plan = link_target.name
		with self.assertRaisesRegex(frappe.ValidationError, "superseded by an approved replacement"):
			plan.save(ignore_permissions=True)
		plan.reload()
		self.assertEqual(plan.plan_status, "Active")
		self.assertFalse(plan.replacement_plan)
		caller_spoof = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_a,
				"week_commencing": add_days(nowdate(), 2),
				"plan_status": "Draft",
				"previous_plan": plan.name,
				"plan_version": plan.plan_version + 1,
				"effective_from": add_days(nowdate(), 2),
				"review_date": add_days(nowdate(), 32),
				"approved_by": self.worker,
				"approved_on": "2000-01-01 00:00:00",
				"purpose_evidence_status": "Recorded",
				"medication_items": [self._item_payload("Spoof")],
			}
		).insert(ignore_permissions=True)
		caller_spoof.plan_status = "Active"
		with self._as_user(self.care_manager):
			caller_spoof.save()
		self.assertEqual(caller_spoof.approved_by, self.care_manager)
		self.assertNotEqual(str(caller_spoof.approved_on), "2000-01-01 00:00:00")
		worker_plan = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_a,
				"week_commencing": add_days(nowdate(), 4),
				"plan_status": "Draft",
				"effective_from": add_days(nowdate(), 4),
				"review_date": add_days(nowdate(), 34),
				"purpose_evidence_status": "Recorded",
				"medication_items": [self._item_payload("Worker Denied")],
			}
		).insert(ignore_permissions=True)
		worker_plan.plan_status = "Active"
		with self._as_user(self.worker), self.assertRaises(frappe.PermissionError):
			worker_plan.save(ignore_permissions=True)

	def test_r3_t006_needs_review_to_active_is_denied(self):
		for status in ("Active", "Superseded", "Archived"):
			with self.subTest(initial_status=status), self.assertRaises(frappe.ValidationError):
				frappe.get_doc(
					{
						"doctype": "Medication Administration Log",
						"participant": self.participant_a,
						"week_commencing": nowdate(),
						"plan_status": status,
						"effective_from": nowdate(),
						"review_date": add_days(nowdate(), 30),
						"purpose_evidence_status": "Recorded",
						"approved_by": self.worker,
						"approved_on": "2000-01-01 00:00:00",
						"medication_items": [self._item_payload(f"Direct {status}")],
					}
				).insert(ignore_permissions=True)
		plan = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_a,
				"week_commencing": nowdate(),
				"plan_status": "Needs Review",
				"medication_items": [self._item_payload("Denied")],
			}
		).insert(ignore_permissions=True)
		plan.plan_status = "Active"
		with self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)

	def test_r3_t007_overlapping_active_plans_are_denied(self):
		self._active_plan(effective_from=nowdate())
		with self.assertRaises(frappe.ValidationError):
			self._active_plan(label="Overlap", effective_from=nowdate())
		bad_period = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_a,
				"week_commencing": add_days(nowdate(), 10),
				"plan_status": "Draft",
				"effective_from": add_days(nowdate(), 10),
				"effective_to": add_days(nowdate(), 9),
				"review_date": add_days(nowdate(), 30),
				"purpose_evidence_status": "Recorded",
				"medication_items": [self._item_payload("Bad Period")],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			bad_period.insert(ignore_permissions=True)
		bad_period.plan_status = "Active"
		with self.assertRaises(frappe.ValidationError):
			bad_period.save(ignore_permissions=True)
		bad_review = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_b,
				"week_commencing": add_days(nowdate(), 10),
				"plan_status": "Draft",
				"effective_from": add_days(nowdate(), 10),
				"review_date": add_days(nowdate(), 9),
				"purpose_evidence_status": "Recorded",
				"medication_items": [self._item_payload("Bad Review")],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			bad_review.insert(ignore_permissions=True)
		bad_review.plan_status = "Active"
		with self.assertRaises(frappe.ValidationError):
			bad_review.save(ignore_permissions=True)

	def test_r3_t008_replacement_supersedes_previous_without_rewriting_events(self):
		plan = self._active_plan()
		approved_by = plan.approved_by
		approved_on = plan.approved_on
		plan.plan_version = plan.plan_version + 1
		with self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)
		plan.reload()
		plan.previous_plan = "caller-spoof"
		with self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)
		plan.reload()
		plan.approved_by = self.worker
		with self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)
		plan.reload()
		plan.approved_on = "2000-01-01 00:00:00"
		with self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)
		plan.reload()
		plan.save(ignore_permissions=True)
		self.assertEqual(plan.approved_by, approved_by)
		self.assertEqual(plan.approved_on, approved_on)
		self._competency()
		event = self._event(plan=plan).insert(ignore_permissions=True)
		with self._as_user(self.worker):
			event.submit()
		plan.reload()
		original_effective_from = plan.effective_from
		original_effective_to = plan.effective_to
		plan.effective_from = add_days(nowdate(), -2)
		with self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)
		plan.reload()
		plan.effective_to = add_days(nowdate(), 7)
		with self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)
		plan.reload()
		self.assertEqual(plan.effective_from, original_effective_from)
		self.assertEqual(plan.effective_to, original_effective_to)
		replacement = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_a,
				"week_commencing": add_days(nowdate(), 1),
				"plan_status": "Draft",
				"plan_version": 2,
				"effective_from": add_days(nowdate(), 1),
				"review_date": add_days(nowdate(), 31),
				"previous_plan": plan.name,
				"approved_by": self.care_manager,
				"approved_on": now_datetime(),
				"purpose_evidence_status": "Recorded",
				"change_reason": f"{RUN_PREFIX} replacement",
				"medication_items": [self._item_payload("Replacement")],
			}
		).insert(ignore_permissions=True)
		replacement.plan_status = "Active"
		replacement.save(ignore_permissions=True)
		plan.reload()
		event.reload()
		self.assertEqual(plan.plan_status, "Superseded")
		self.assertEqual(plan.approved_by, approved_by)
		self.assertEqual(plan.approved_on, approved_on)
		self.assertEqual(plan.effective_from, original_effective_from)
		self.assertEqual(plan.effective_to, original_effective_to)
		self.assertEqual(plan.replacement_plan, replacement.name)
		self.assertEqual(replacement.plan_version, plan.plan_version + 1)
		self.assertEqual(event.medication_plan, plan.name)
		self._assert_locked_field_denied(plan, "plan_version", plan.plan_version + 1)
		self._assert_locked_field_denied(plan, "previous_plan", replacement.name)
		self._assert_locked_field_denied(plan, "approved_by", self.worker)
		self._assert_locked_field_denied(plan, "approved_on", "2000-01-01 00:00:00")
		self._assert_locked_field_denied(plan, "effective_from", add_days(nowdate(), -10))
		self._assert_locked_field_denied(plan, "effective_to", add_days(nowdate(), 10))
		self._assert_locked_field_denied(plan, "replacement_plan", "")
		replacement_approved_by = replacement.approved_by
		replacement_approved_on = replacement.approved_on
		replacement.save(ignore_permissions=True)
		plan.reload()
		replacement.reload()
		self.assertEqual(replacement.plan_status, "Active")
		self.assertEqual(replacement.approved_by, replacement_approved_by)
		self.assertEqual(replacement.approved_on, replacement_approved_on)
		self.assertEqual(plan.plan_status, "Superseded")
		self.assertEqual(plan.replacement_plan, replacement.name)
		plan.plan_status = "Archived"
		plan.lifecycle_reason = f"{RUN_PREFIX} archive superseded plan"
		plan.save(ignore_permissions=True)
		self.assertEqual(plan.plan_status, "Archived")
		for fieldname, value in (
			("plan_version", plan.plan_version + 1),
			("previous_plan", replacement.name),
			("approved_by", self.worker),
			("approved_on", "2000-01-01 00:00:00"),
			("effective_from", add_days(nowdate(), -20)),
			("effective_to", add_days(nowdate(), 20)),
			("replacement_plan", ""),
		):
			self._assert_locked_field_denied(plan, fieldname, value)
		event.reload()
		self.assertEqual(event.medication_plan, plan.name)
		replacement.save(ignore_permissions=True)
		plan.reload()
		replacement.reload()
		self.assertEqual(replacement.plan_status, "Active")
		self.assertEqual(replacement.approved_by, replacement_approved_by)
		self.assertEqual(replacement.approved_on, replacement_approved_on)
		self.assertEqual(plan.plan_status, "Archived")
		self.assertEqual(plan.replacement_plan, replacement.name)
		bad_status = self._active_plan(participant=self.participant_b, label="Bad Status", effective_from=add_days(nowdate(), 10))
		bad_status.plan_status = "Archived"
		bad_status.lifecycle_reason = f"{RUN_PREFIX} archive bad status"
		bad_status.save(ignore_permissions=True)
		bad_relationship = self._draft_plan(
			participant=self.participant_b,
			label="Bad Relationship",
			effective_from=add_days(nowdate(), 11),
			previous_plan=bad_status.name,
			plan_version=bad_status.plan_version + 1,
		)
		bad_relationship.plan_status = "Active"
		with self.assertRaisesRegex(frappe.ValidationError, "active plan"):
			bad_relationship.save(ignore_permissions=True)

	def test_r3_t009_activation_denied_without_required_safe_use_information(self):
		plan = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_a,
				"week_commencing": nowdate(),
				"plan_status": "Draft",
				"effective_from": nowdate(),
				"review_date": add_days(nowdate(), 30),
				"approved_by": self.care_manager,
				"approved_on": now_datetime(),
				"medication_items": [{"medication_name": f"{RUN_PREFIX} Unsafe", "time_slot": "8 AM"}],
			}
		).insert(ignore_permissions=True)
		plan.plan_status = "Active"
		with self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)
		for label, updates in (
			("PRN", {"is_prn": 1}),
			("Controlled", {"is_controlled_drug": 1}),
			("Injection", {"route": "Injection"}),
			("Inhaled", {"route": "Inhaled"}),
		):
			item = self._item_payload(label)
			item.update(updates)
			plan = frappe.get_doc(
				{
					"doctype": "Medication Administration Log",
					"participant": self.participant_b,
					"week_commencing": add_days(nowdate(), 20),
					"plan_status": "Draft",
					"effective_from": add_days(nowdate(), 20),
					"review_date": add_days(nowdate(), 40),
					"purpose_evidence_status": "Recorded",
					"medication_items": [item],
				}
			).insert(ignore_permissions=True)
			plan.plan_status = "Active"
			with self.subTest(label=label), self.assertRaises(frappe.ValidationError):
				plan.save(ignore_permissions=True)

	def test_r3_t010_plan_item_material_change_after_event_is_denied(self):
		plan = self._active_plan()
		self._competency()
		event = self._event(plan=plan).insert(ignore_permissions=True)
		with self._as_user(self.worker):
			event.submit()
		plan.medication_items[0].prescribed_dose = "20"
		with self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)
		plan.reload()
		plan.medication_items = []
		with self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)
		plan.reload()
		event.reload()
		self.assertEqual(event.medication_plan, plan.name)
		self.assertEqual(event.medication_plan_item, plan.medication_items[0].name)
		plan.set("medication_items", [self._item_payload("Replacement Row")])
		with self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)

	def test_r3_t011_participant_cannot_change_after_first_save(self):
		plan = self._active_plan()
		plan.participant = self.participant_b
		with self.assertRaises(frappe.ValidationError):
			plan.save(ignore_permissions=True)

	def test_r3_t012_active_superseded_archived_plans_cannot_be_deleted(self):
		plan = self._active_plan()
		with self.assertRaises(frappe.ValidationError):
			plan.delete(ignore_permissions=True)

	def test_r3_t013_outcome_required_before_finalization(self):
		plan = self._active_plan()
		self._competency()
		event = self._event(plan=plan, outcome="")
		event.insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			event.submit()
		event = self._event(plan=plan, scheduled_datetime=f"{add_days(nowdate(), 1)} 08:00:00")
		event.prescribed_dose = "999"
		event.dose_unit = "ml"
		event.route = "Topical"
		event.insert(ignore_permissions=True)
		self.assertEqual(event.prescribed_dose, plan.medication_items[0].prescribed_dose)
		self.assertEqual(event.dose_unit, plan.medication_items[0].dose_unit)
		self.assertEqual(event.route, plan.medication_items[0].route)
		self.assertFalse(event.finalized_by)
		with self._as_user(self.worker):
			event.submit()
		self.assertEqual(event.finalized_by, self.worker)
		self.assertTrue(event.finalized_on)
		no_dose = self._event(plan=plan, scheduled_datetime=f"{add_days(nowdate(), 2)} 08:00:00")
		no_dose.administered_dose = ""
		no_dose.insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			no_dose.submit()
		variance = self._event(plan=plan, scheduled_datetime=f"{add_days(nowdate(), 3)} 08:00:00")
		variance.administered_dose = "5"
		variance.insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			variance.submit()

	def test_r3_t014_duplicate_administration_evidence_is_denied(self):
		plan = self._active_plan()
		self._competency()
		event = self._event(plan=plan)
		event.occurrence_key = "caller-spoof"
		event.insert(ignore_permissions=True)
		with self._as_user(self.worker):
			event.submit()
		self.assertNotEqual(event.occurrence_key, "caller-spoof")
		self.assertTrue(event.occurrence_key)
		meta = frappe.get_meta("Medication Administration Event")
		occurrence = meta.get_field("occurrence_key")
		self.assertTrue(occurrence.read_only)
		self.assertTrue(occurrence.unique)
		with self.assertRaises(frappe.ValidationError):
			self._event(plan=plan).insert(ignore_permissions=True)

	def test_r3_t015_plan_item_must_belong_to_selected_plan(self):
		plan = self._active_plan()
		other = self._active_plan(participant=self.participant_b, label="Other", effective_from=add_days(nowdate(), 1))
		self._competency()
		event = self._event(plan=plan)
		event.medication_plan_item = other.medication_items[0].name
		with self.assertRaises(frappe.ValidationError):
			event.insert(ignore_permissions=True)
		event = self._event(plan=plan)
		event.incident = _incident(self.participant_b, "Mismatch")
		with self.assertRaises(frappe.PermissionError):
			event.insert(ignore_permissions=True)

	def test_r3_t016_altered_scheduled_time_cannot_spoof_occurrence(self):
		plan = self._active_plan()
		self._competency()
		event = self._event(plan=plan, scheduled_datetime=_today_at(9))
		with self.assertRaises(frappe.ValidationError):
			event.insert(ignore_permissions=True)
		outside = self._event(plan=plan, scheduled_datetime=f"{add_days(nowdate(), -1)} 08:00:00")
		with self.assertRaises(frappe.ValidationError):
			outside.insert(ignore_permissions=True)
		selected = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_b,
				"week_commencing": nowdate(),
				"plan_status": "Draft",
				"effective_from": nowdate(),
				"review_date": add_days(nowdate(), 30),
				"purpose_evidence_status": "Recorded",
				"medication_items": [
					{
						**self._item_payload("Selected"),
						"frequency": "Selected Days",
						"monday": 0,
						"tuesday": 0,
						"wednesday": 0,
						"thursday": 0,
						"friday": 0,
						"saturday": 0,
						"sunday": 0,
					}
				],
			}
		).insert(ignore_permissions=True)
		selected.plan_status = "Active"
		with self.assertRaises(frappe.ValidationError):
			selected.save(ignore_permissions=True)

	def test_r3_t017_active_competency_required_for_worker_finalization(self):
		plan = self._active_plan()
		event = self._event(plan=plan).insert(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			event.submit()
		comp = self._competency()
		with self.assertRaises(frappe.ValidationError):
			comp.delete(ignore_permissions=True)
		meta = frappe.get_meta("Medication Competency")
		roles = {row.role: row for row in meta.permissions}
		self.assertNotIn("Support Worker", roles)

	def test_r3_t018_expired_or_inactive_competency_is_denied(self):
		plan = self._active_plan(label="T018", effective_from=nowdate(), effective_to=add_days(nowdate(), 4))
		for offset, label, worker, setup in (
			(1, "absent", self.role_only_worker, lambda scheduled_date: None),
			(
				2,
				"expired",
				self.worker,
				lambda scheduled_date: self._competency(
					self.worker,
					status="Active",
					valid_from=add_days(scheduled_date, -10),
					expiry_date=nowdate(),
				),
			),
			(3, "inactive", self.worker_b, lambda scheduled_date: self._inactive_competency(self.worker_b, scheduled_date)),
			(4, "revoked", self.worker_b, lambda scheduled_date: self._competency(self.worker_b, status="Revoked", valid_from=add_days(scheduled_date, -1), expiry_date=add_days(scheduled_date, 10))),
		):
			scheduled_date = add_days(nowdate(), offset)
			if worker in {self.worker_b, self.role_only_worker}:
				_ensure_grant(worker, self.participant_a)
			setup(scheduled_date)
			event = self._event(plan=plan, worker=worker, task=None, scheduled_datetime=f"{scheduled_date} 08:00:00").insert(
				ignore_permissions=True
			)
			with self.subTest(label=label), self._as_user(worker), self.assertRaises(frappe.PermissionError):
				event.submit()
		control_plan = self._active_plan(label="T018 Control", effective_from=add_days(nowdate(), 10))
		self._competency(self.worker, valid_from=add_days(nowdate(), 9), expiry_date=add_days(nowdate(), 20))
		allowed = self._event(plan=control_plan, scheduled_datetime=f"{add_days(nowdate(), 10)} 08:00:00").insert(
			ignore_permissions=True
		)
		with self._as_user(self.worker):
			allowed.submit()
		self.assertEqual(allowed.finalized_by, self.worker)

	def test_r3_t019_support_worker_role_alone_does_not_authorize_administration(self):
		plan = self._active_plan()
		self._competency(self.role_only_worker)
		event = self._event(plan=plan, worker=self.role_only_worker, task=None).insert(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			event.submit()
		self._competency(self.worker)
		task = self._medication_task(plan, self.worker, "T019")
		with self._as_user(self.worker):
			worker_event = self._event(
				plan=plan,
				worker=self.worker,
				task=task,
				scheduled_datetime=f"{add_days(nowdate(), 1)} 08:00:00",
			).insert()
			self.assertFalse(worker_event.flags.ignore_permissions)
			worker_event.submit()
		self.assertEqual(worker_event.finalized_by, self.worker)
		cross_plan = self._active_plan(participant=self.participant_b, label="T019 Cross")
		cross_event = self._event(
			plan=cross_plan,
			worker=self.worker,
			task=None,
			scheduled_datetime=f"{add_days(nowdate(), 12)} 08:00:00",
		)
		with self._as_user(self.worker), self.assertRaises(frappe.PermissionError):
			cross_event.insert()
		event_b = self._event(
			plan=cross_plan,
			worker=self.worker_b,
			task=None,
			scheduled_datetime=f"{add_days(nowdate(), 12)} 08:00:00",
		).insert(ignore_permissions=True)
		with self._as_user(self.worker):
			self.assertTrue(
				frappe.has_permission("Medication Administration Event", "read", doc=worker_event)
			)
			self.assertFalse(
				frappe.has_permission("Medication Administration Event", "read", doc=event_b)
			)
			rows = frappe.get_list(
				"Medication Administration Event",
				fields=["name"],
				filters={"name": ["in", [worker_event.name, event_b.name]]},
				limit=10,
			)
		self.assertEqual({row.name for row in rows}, {worker_event.name})
		self._competency(self.worker_b)
		_grant(self.worker_b, self.participant_a)
		spoof = self._event(plan=plan, worker=self.worker_b, task=None, scheduled_datetime=f"{add_days(nowdate(), 2)} 08:00:00").insert(ignore_permissions=True)
		with self._as_user(self.worker), self.assertRaises(frappe.PermissionError):
			spoof.submit()
		manager_event = self._event(plan=plan, task=task, scheduled_datetime=f"{add_days(nowdate(), 3)} 08:00:00").insert(ignore_permissions=True)
		with self._as_user(self.care_manager), self.assertRaises(frappe.PermissionError):
			manager_event.submit()
		manager_reason_event = self._event(plan=plan, task=task, scheduled_datetime=f"{add_days(nowdate(), 4)} 08:00:00").insert(ignore_permissions=True)
		manager_reason_event.administrative_override_reason = "Care Manager must still be denied"
		with self._as_user(self.care_manager), self.assertRaises(frappe.PermissionError):
			manager_reason_event.submit()
		self._competency(self.care_worker)
		care_worker_task = self._medication_task(plan, self.care_worker, "Care Worker")
		care_worker_event = self._event(
			plan=plan,
			worker=self.care_worker,
			task=care_worker_task,
			scheduled_datetime=f"{add_days(nowdate(), 11)} 08:00:00",
		).insert(ignore_permissions=True)
		care_worker_event.administrative_override_reason = "Care Manager plus worker remains denied"
		with self._as_user(self.care_worker), self.assertRaises(frappe.PermissionError):
			care_worker_event.submit()
		unqualified_override = self._event(plan=plan, worker=self.role_only_worker, task=None, scheduled_datetime=f"{add_days(nowdate(), 5)} 08:00:00").insert(ignore_permissions=True)
		unqualified_override.administrative_override_reason = "Unqualified worker remains denied"
		with self._as_user("Administrator"), self.assertRaises(frappe.PermissionError):
			unqualified_override.submit()
		missing_override = self._event(plan=plan, task=task, scheduled_datetime=f"{add_days(nowdate(), 6)} 08:00:00").insert(ignore_permissions=True)
		with self._as_user("Administrator"), self.assertRaises(frappe.PermissionError):
			missing_override.submit()
		override = self._event(plan=plan, task=task, scheduled_datetime=f"{add_days(nowdate(), 7)} 08:00:00").insert(ignore_permissions=True)
		override.administrative_override_reason = "Observed and documented override"
		with self._as_user("Administrator"):
			override.submit()
		self.assertEqual(override.finalized_by, "Administrator")
		self.assertEqual(override.worker, self.worker)
		self.assertTrue(override.finalized_on)
		system_missing = self._event(plan=plan, task=task, scheduled_datetime=f"{add_days(nowdate(), 8)} 08:00:00").insert(ignore_permissions=True)
		with self._as_user(self.system_manager), self.assertRaises(frappe.PermissionError):
			system_missing.submit()
		system_override = self._event(plan=plan, task=task, scheduled_datetime=f"{add_days(nowdate(), 9)} 08:00:00").insert(ignore_permissions=True)
		system_override.administrative_override_reason = "System Manager audited override"
		with self._as_user(self.system_manager):
			system_override.submit()
		self.assertEqual(system_override.finalized_by, self.system_manager)
		self.assertEqual(system_override.worker, self.worker)
		mixed_override = self._event(plan=plan, task=task, scheduled_datetime=f"{add_days(nowdate(), 10)} 08:00:00").insert(ignore_permissions=True)
		mixed_override.administrative_override_reason = "Mixed manager follows System Manager precedence"
		with self._as_user(self.mixed_manager):
			mixed_override.submit()
		self.assertEqual(mixed_override.finalized_by, self.mixed_manager)
		self.assertEqual(mixed_override.worker, self.worker)

	def test_r3_t020_task_bound_event_requires_authoritative_assignment(self):
		plan = self._active_plan()
		self._competency(self.role_only_worker)
		_grant(self.role_only_worker, self.participant_a)
		event = self._event(plan=plan, worker=self.role_only_worker, task=self._medication_task(plan, self.worker)).insert(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			event.submit()
		unrelated = self._support_task(self.support_plan, "Unrelated", self.worker)
		event = self._event(plan=plan, task=unrelated, scheduled_datetime=f"{add_days(nowdate(), 1)} 08:00:00")
		with self.assertRaises(frappe.ValidationError):
			event.insert(ignore_permissions=True)
		blank_context = self._support_task(self.support_plan, "Blank Row", self.worker, source_doc=plan, source_row_id="")
		event = self._event(plan=plan, task=blank_context, scheduled_datetime=f"{add_days(nowdate(), 2)} 08:00:00")
		with self.assertRaises(frappe.ValidationError):
			event.insert(ignore_permissions=True)
		wrong_context = self._support_task(self.support_plan, "Wrong Row", self.worker, source_doc=plan, source_row_id="wrong-row")
		event = self._event(plan=plan, task=wrong_context, scheduled_datetime=f"{add_days(nowdate(), 3)} 08:00:00")
		with self.assertRaises(frappe.ValidationError):
			event.insert(ignore_permissions=True)
		exact_context = self._support_task(
			self.support_plan,
			"Exact Row",
			self.worker,
			source_doc=plan,
			source_row_id=plan.medication_items[0].name,
		)
		event = self._event(plan=plan, task=exact_context, scheduled_datetime=f"{add_days(nowdate(), 4)} 08:00:00")
		event.insert(ignore_permissions=True)

	def test_r3_t021_referenced_selected_weekday_history_is_immutable_on_parent_save(self):
		plan, event, selected_weekday, alternate_weekday = self._selected_days_plan_with_event("T021")
		plan.medication_items[0].set(selected_weekday, 0)
		plan.medication_items[0].set(alternate_weekday, 1)
		with self.assertRaisesRegex(frappe.ValidationError, "materially changed"):
			plan.save(ignore_permissions=True)
		plan.reload()
		event.reload()
		self.assertEqual(plan.medication_items[0].get(selected_weekday), 1)
		self.assertEqual(event.medication_plan_item, plan.medication_items[0].name)

	def test_r3_t022_referenced_selected_weekday_history_is_immutable_on_child_save(self):
		plan, event, selected_weekday, alternate_weekday = self._selected_days_plan_with_event("T022")
		child = frappe.get_doc("Medication Plan Item", plan.medication_items[0].name)
		child.set(selected_weekday, 0)
		child.set(alternate_weekday, 1)
		with self.assertRaisesRegex(frappe.ValidationError, "materially changed"):
			child.save(ignore_permissions=True)
		child.reload()
		event.reload()
		self.assertEqual(child.get(selected_weekday), 1)
		self.assertEqual(event.medication_plan_item, child.name)

	def test_r3_t023_referenced_plan_item_cannot_be_deleted_or_reparented_directly(self):
		plan, event, _, _ = self._selected_days_plan_with_event("T023")
		child = frappe.get_doc("Medication Plan Item", plan.medication_items[0].name)
		with self.assertRaises(frappe.ValidationError):
			child.delete(ignore_permissions=True)
		child.reload()
		other_plan = self._active_plan(participant=self.participant_b, label="T023 Other", effective_from=add_days(nowdate(), 5))
		child.parent = other_plan.name
		with self.assertRaisesRegex(frappe.ValidationError, "materially changed|removed|reparented"):
			child.save(ignore_permissions=True)
		event.reload()
		self.assertEqual(event.medication_plan_item, plan.medication_items[0].name)

	def test_r3_t024_serialized_equivalent_values_do_not_rewrite_history(self):
		plan, event, _, _ = self._selected_days_plan_with_event("T024")
		approved_by = plan.approved_by
		approved_on = plan.approved_on
		payload = json.loads(frappe.as_json(frappe.get_doc("Medication Administration Log", plan.name).as_dict()))
		round_tripped = frappe.get_doc(payload)
		round_tripped.save(ignore_permissions=True)
		round_tripped.reload()
		event.reload()
		self.assertEqual(round_tripped.approved_by, approved_by)
		self.assertEqual(round_tripped.approved_on, approved_on)
		self.assertEqual(event.medication_plan, round_tripped.name)

	def test_r3_t025_active_plan_direct_child_safety_checks_are_enforced_before_first_event(self):
		for offset, (label, updates, message) in enumerate((
			("PRN", {"is_prn": 1}, "PRN"),
			("Controlled", {"is_controlled_drug": 1}, "Controlled"),
			("Injection", {"route": "Injection"}, "Specialist"),
			("Inhaled", {"route": "Inhaled"}, "Specialist"),
			("Missing Dose", {"prescribed_dose": ""}, "complete safe-use"),
			("Unknown Frequency", {"frequency": "Every Lunar Cycle"}, "Unknown medication frequency"),
			("No Selected Day", {"frequency": "Selected Days"}, "Selected-day"),
		)):
			effective_from = add_days(nowdate(), 20 + offset)
			plan = self._active_plan(label=f"T025 {label}", effective_from=effective_from)
			child = frappe.get_doc("Medication Plan Item", plan.medication_items[0].name)
			child.update(updates)
			if label == "No Selected Day":
				for weekday in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
					child.set(weekday, 0)
			with self.subTest(label=label), self.assertRaisesRegex(frappe.ValidationError, message):
				child.save(ignore_permissions=True)
			plan.reload()
			self.assertEqual(plan.medication_items[0].prescribed_dose, "10")
			self.assertEqual(plan.medication_items[0].route, "Oral")
			self.assertEqual(plan.medication_items[0].frequency, "Daily")
			plan.effective_to = effective_from
			plan.save(ignore_permissions=True)

	def test_r3_t026_active_plan_direct_child_insert_and_delete_cannot_bypass_parent_invariants(self):
		plan = self._active_plan(label="T026", effective_from=add_days(nowdate(), 30))
		unsafe_child = frappe.get_doc(
			{
				"doctype": "Medication Plan Item",
				"parent": plan.name,
				"parenttype": "Medication Administration Log",
				"parentfield": "medication_items",
				**self._item_payload("T026 Unsafe"),
				"is_controlled_drug": 1,
			}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "Controlled-drug"):
			unsafe_child.insert(ignore_permissions=True)
		child = frappe.get_doc("Medication Plan Item", plan.medication_items[0].name)
		with self.assertRaisesRegex(frappe.ValidationError, "at least one active"):
			child.delete(ignore_permissions=True)
		plan.reload()
		self.assertEqual(len([row for row in plan.medication_items if row.get("is_active", 1)]), 1)

	def test_r3_t027_event_validation_fails_closed_for_unsafe_item_state_from_database(self):
		plan = self._active_plan(label="T027", effective_from=add_days(nowdate(), 40))
		child_name = plan.medication_items[0].name
		frappe.db.set_value("Medication Plan Item", child_name, "is_prn", 1, update_modified=False)
		plan.reload()
		self.assertEqual(plan.medication_items[0].is_prn, 1)
		self._competency(valid_from=add_days(nowdate(), 39), expiry_date=add_days(nowdate(), 70))
		event = self._event(plan=plan, scheduled_datetime=f"{add_days(nowdate(), 40)} 08:00:00")
		with self.assertRaisesRegex(frappe.ValidationError, "PRN"):
			event.insert(ignore_permissions=True)

	def test_r3_t028_referenced_item_protection_covers_parent_child_and_receiving_parent_paths(self):
		plan, event, _, _ = self._selected_days_plan_with_event("T028")
		protected_updates = {
			"medication_name": "Changed Medication",
			"dosage": "20 mg",
			"route": "Topical",
			"time_slot": "12 PM (Lunch)",
			"medication_form": "Liquid",
			"strength": "20 mg",
			"prescribed_dose": "20",
			"dose_unit": "ml",
			"scheduled_time": "09:00:00",
			"frequency": "Daily",
			"indication": "Changed indication",
			"is_prn": 1,
			"is_controlled_drug": 1,
			"is_active": 0,
			"prn_indication": "Changed PRN",
			"prn_minimum_interval_hours": 4,
			"prn_maximum_dose": "40",
			"monday": 0,
			"tuesday": 0,
			"wednesday": 0,
			"thursday": 0,
			"friday": 0,
			"saturday": 0,
			"sunday": 0,
			"instructions": "Changed instructions",
			"storage_instructions": "Changed storage",
			"side_effects": "Changed side effects",
			"escalation_instructions": "Changed escalation",
		}
		for fieldname in PROTECTED_HISTORY_FIELDS:
			plan.reload()
			original = plan.medication_items[0].get(fieldname)
			new_value = protected_updates[fieldname]
			if new_value == original:
				new_value = "" if original else "Changed"
			plan.medication_items[0].set(fieldname, new_value)
			with self.subTest(path="parent", fieldname=fieldname), self.assertRaisesRegex(
				frappe.ValidationError, "materially changed"
			):
				plan.save(ignore_permissions=True)
			plan.reload()
			self.assertEqual(plan.medication_items[0].get(fieldname), original)
			child = frappe.get_doc("Medication Plan Item", plan.medication_items[0].name)
			child.set(fieldname, new_value)
			with self.subTest(path="child", fieldname=fieldname), self.assertRaisesRegex(
				frappe.ValidationError, "materially changed"
			):
				child.save(ignore_permissions=True)
			child.reload()
			self.assertEqual(child.get(fieldname), original)
		other = self._active_plan(participant=self.participant_b, label="T028 Receiver", effective_from=add_days(nowdate(), 60))
		payload = json.loads(frappe.as_json(other.as_dict()))
		moved_row = json.loads(frappe.as_json(plan.medication_items[0].as_dict()))
		moved_row["parent"] = other.name
		payload["medication_items"].append(moved_row)
		receiving_parent = frappe.get_doc(payload)
		with self.assertRaisesRegex(frappe.ValidationError, "moved"):
			receiving_parent.save(ignore_permissions=True)
		plan.reload()
		other.reload()
		event.reload()
		self.assertEqual(event.medication_plan, plan.name)
		self.assertEqual(event.medication_plan_item, plan.medication_items[0].name)
		self.assertNotIn(plan.medication_items[0].name, [row.name for row in other.medication_items])

	def test_r3_t029_field_aware_history_comparison_accepts_equivalent_values_and_denies_real_changes(self):
		plan, event, _, _ = self._selected_days_plan_with_event("T029")
		plan.effective_to = add_days(nowdate(), 20)
		with self.assertRaisesRegex(frappe.ValidationError, "effective periods"):
			plan.save(ignore_permissions=True)
		plan.reload()
		payload = json.loads(frappe.as_json(plan.as_dict()))
		payload["approved_on"] = str(plan.approved_on)
		payload["medication_items"][0]["scheduled_time"] = "08:00:00"
		round_tripped = frappe.get_doc(payload)
		round_tripped.save(ignore_permissions=True)
		round_tripped.reload()
		event.reload()
		self.assertEqual(round_tripped.approved_by, plan.approved_by)
		self.assertEqual(round_tripped.approved_on, plan.approved_on)
		child = frappe.get_doc("Medication Plan Item", round_tripped.medication_items[0].name)
		child.scheduled_time = "08:00:01"
		with self.assertRaisesRegex(frappe.ValidationError, "materially changed"):
			child.save(ignore_permissions=True)

	def test_r3_t030_submitted_event_edit_cancel_and_delete_remain_denied(self):
		plan = self._active_plan(label="T030", effective_from=add_days(nowdate(), 70))
		self._competency(valid_from=add_days(nowdate(), 69), expiry_date=add_days(nowdate(), 90))
		event = self._event(plan=plan, scheduled_datetime=f"{add_days(nowdate(), 70)} 08:00:00").insert(
			ignore_permissions=True
		)
		with self._as_user(self.worker):
			event.submit()
		event.notes = "Caller attempted submitted edit"
		with self.assertRaises(frappe.ValidationError):
			event.save(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			event.cancel()
		with self.assertRaises(frappe.ValidationError):
			event.delete(ignore_permissions=True)
		event.reload()
		self.assertEqual(event.docstatus, 1)

	def test_r3_t031_direct_child_deactivation_cannot_remove_only_active_item(self):
		plan = self._active_plan(label="T031", effective_from=add_days(nowdate(), 80))
		child = frappe.get_doc("Medication Plan Item", plan.medication_items[0].name)
		child.is_active = 0
		with self.assertRaisesRegex(frappe.ValidationError, "at least one active"):
			child.save(ignore_permissions=True)
		plan.reload()
		self.assertEqual(plan.medication_items[0].name, child.name)
		self.assertEqual(plan.medication_items[0].is_active, 1)

	def test_r3_t032_direct_child_move_cannot_remove_only_active_item_from_source_plan(self):
		source = self._active_plan_with_two_items("T032 Source", effective_from=add_days(nowdate(), 85))
		destination = self._active_plan(
			participant=self.participant_b,
			label="T032 Destination",
			effective_from=add_days(nowdate(), 85),
		)
		child = frappe.get_doc("Medication Plan Item", source.medication_items[0].name)
		child.parent = destination.name
		with self.assertRaisesRegex(frappe.ValidationError, "participant"):
			child.save(ignore_permissions=True)
		source.reload()
		destination.reload()
		self.assertIn(child.name, [row.name for row in source.medication_items])
		self.assertNotIn(child.name, [row.name for row in destination.medication_items])

	def test_r3_t033_unreferenced_safe_child_change_succeeds_when_active_sibling_remains(self):
		plan = self._active_plan(label="T033", effective_from=add_days(nowdate(), 90))
		plan.append("medication_items", self._item_payload("T033 Second"))
		plan.save(ignore_permissions=True)
		first = frappe.get_doc("Medication Plan Item", plan.medication_items[0].name)
		first.is_active = 0
		first.instructions = "Safe unreferenced update with active sibling retained"
		first.save(ignore_permissions=True)
		plan.reload()
		rows = {row.name: row for row in plan.medication_items}
		self.assertEqual(rows[first.name].is_active, 0)
		self.assertEqual(rows[first.name].instructions, "Safe unreferenced update with active sibling retained")
		self.assertTrue(any(row.get("is_active", 1) for row in plan.medication_items))

	def test_r3_t034_receiving_parent_json_cannot_orphan_source_active_plan(self):
		source = self._active_plan(
			label="T034 Source",
			effective_from=add_days(nowdate(), 100),
			effective_to=add_days(nowdate(), 100),
		)
		destination = self._active_plan(
			participant=self.participant_a,
			label="T034 Destination",
			effective_from=add_days(nowdate(), 101),
		)
		moved_name = source.medication_items[0].name
		payload = json.loads(frappe.as_json(destination.as_dict()))
		moved_row = json.loads(frappe.as_json(source.medication_items[0].as_dict()))
		moved_row["parent"] = destination.name
		payload["medication_items"].append(moved_row)
		with self.assertRaisesRegex(frappe.ValidationError, "at least one active"):
			frappe.get_doc(payload).save(ignore_permissions=True)
		source.reload()
		destination.reload()
		self.assertEqual([row.name for row in source.medication_items], [moved_name])
		self.assertNotIn(moved_name, [row.name for row in destination.medication_items])
		self.assertTrue(any(row.get("is_active", 1) for row in source.medication_items))

	def test_r3_t035_receiving_parent_document_cannot_orphan_source_active_plan(self):
		source = self._active_plan(
			label="T035 Source",
			effective_from=add_days(nowdate(), 105),
			effective_to=add_days(nowdate(), 105),
		)
		destination = self._active_plan(
			participant=self.participant_a,
			label="T035 Destination",
			effective_from=add_days(nowdate(), 106),
		)
		moved_name = source.medication_items[0].name
		destination.append("medication_items", json.loads(frappe.as_json(source.medication_items[0].as_dict())))
		destination.medication_items[-1].parent = destination.name
		with self.assertRaisesRegex(frappe.ValidationError, "at least one active"):
			destination.save(ignore_permissions=True)
		source.reload()
		destination.reload()
		self.assertEqual([row.name for row in source.medication_items], [moved_name])
		self.assertNotIn(moved_name, [row.name for row in destination.medication_items])

	def test_r3_t036_receiving_parent_move_is_allowed_when_source_keeps_active_sibling(self):
		source = self._active_plan_with_two_items("T036 Source", effective_from=add_days(nowdate(), 110))
		source.effective_to = add_days(nowdate(), 110)
		source.save(ignore_permissions=True)
		destination = self._active_plan(
			participant=self.participant_a,
			label="T036 Destination",
			effective_from=add_days(nowdate(), 111),
			effective_to=add_days(nowdate(), 114),
		)
		moved_name = source.medication_items[0].name
		remaining_name = source.medication_items[1].name
		payload = json.loads(frappe.as_json(destination.as_dict()))
		moved_row = json.loads(frappe.as_json(source.medication_items[0].as_dict()))
		moved_row["parent"] = destination.name
		payload["medication_items"].append(moved_row)
		frappe.get_doc(payload).save(ignore_permissions=True)
		source.reload()
		destination.reload()
		self.assertEqual([row.name for row in source.medication_items], [remaining_name])
		self.assertIn(moved_name, [row.name for row in destination.medication_items])
		self.assertTrue(any(row.get("is_active", 1) for row in source.medication_items))
		cross_source = self._active_plan_with_two_items("T036 Cross Source", effective_from=add_days(nowdate(), 115))
		cross_source.effective_to = add_days(nowdate(), 115)
		cross_source.save(ignore_permissions=True)
		cross_destination = self._active_plan(
			participant=self.participant_b,
			label="T036 Cross Destination",
			effective_from=add_days(nowdate(), 115),
		)
		cross_name = cross_source.medication_items[0].name
		payload = json.loads(frappe.as_json(cross_destination.as_dict()))
		cross_row = json.loads(frappe.as_json(cross_source.medication_items[0].as_dict()))
		cross_row["parent"] = cross_destination.name
		payload["medication_items"].append(cross_row)
		with self.assertRaisesRegex(frappe.ValidationError, "participant"):
			frappe.get_doc(payload).save(ignore_permissions=True)
		cross_source.reload()
		cross_destination.reload()
		self.assertIn(cross_name, [row.name for row in cross_source.medication_items])
		self.assertNotIn(cross_name, [row.name for row in cross_destination.medication_items])
		copy_payload = json.loads(frappe.as_json(cross_destination.as_dict()))
		new_row = json.loads(frappe.as_json(cross_source.medication_items[0].as_dict()))
		new_row.pop("name", None)
		new_row.pop("__unsaved", None)
		new_row["parent"] = cross_destination.name
		copy_payload["medication_items"].append(new_row)
		frappe.get_doc(copy_payload).save(ignore_permissions=True)
		cross_destination.reload()
		self.assertNotIn(cross_name, [row.name for row in cross_destination.medication_items])
		self.assertEqual(len(cross_destination.medication_items), 2)

	def test_r3_t037_blank_defaults_and_invalid_lifecycle_states_are_isolated(self):
		blank = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": self.participant_a,
				"week_commencing": nowdate(),
				"medication_items": [self._item_payload("T037 Blank")],
			}
		).insert(ignore_permissions=True)
		self.assertEqual(blank.plan_status, "Needs Review")
		blank.plan_status = ""
		with self.assertRaisesRegex(frappe.ValidationError, "status"):
			blank.save(ignore_permissions=True)
		blank.reload()
		self.assertEqual(blank.plan_status, "Needs Review")
		draft = self._draft_plan(label="T037 Draft", effective_from=add_days(nowdate(), 112))
		draft.plan_status = ""
		with self.assertRaisesRegex(frappe.ValidationError, "status"):
			draft.save(ignore_permissions=True)
		draft.reload()
		self.assertEqual(draft.plan_status, "Draft")
		draft.plan_status = "Reviewless"
		with self.assertRaisesRegex(frappe.ValidationError, "status|not allowed|start"):
			draft.save(ignore_permissions=True)
		draft.reload()
		self.assertEqual(draft.plan_status, "Draft")
		active = self._active_plan(label="T037 Active", effective_from=add_days(nowdate(), 113))
		active.plan_status = ""
		with self.assertRaisesRegex(frappe.ValidationError, "status"):
			active.save(ignore_permissions=True)
		active.reload()
		self.assertEqual(active.plan_status, "Active")
		active.plan_status = "Reviewless"
		with self.assertRaisesRegex(frappe.ValidationError, "status|not allowed|superseded|archived"):
			active.save(ignore_permissions=True)
		active.reload()
		self.assertEqual(active.plan_status, "Active")

	def test_r3_t038_predecessor_invalid_conditions_are_independent(self):
		base = self._active_plan(
			label="T038 Base",
			effective_from=add_days(nowdate(), 120),
			effective_to=add_days(nowdate(), 120),
		)
		cases = (
			("invalid-status", self._draft_plan(label="T038 Draft Previous", effective_from=add_days(nowdate(), 121)), self.participant_a, 2),
			("wrong-participant", self._active_plan(participant=self.participant_b, label="T038 Wrong Participant", effective_from=add_days(nowdate(), 121)), self.participant_a, 2),
			("wrong-version", base, self.participant_a, 7),
		)
		for label, previous, participant, version in cases:
			replacement = self._draft_plan(
				participant=participant,
				label=f"T038 {label}",
				effective_from=add_days(nowdate(), 122 + len(label)),
				previous_plan=previous.name,
				plan_version=version,
			)
			replacement.plan_status = "Active"
			with self.subTest(label=label), self.assertRaises(frappe.ValidationError):
				replacement.save(ignore_permissions=True)
			previous.reload()
			self.assertNotEqual(previous.replacement_plan, replacement.name)
		good = self._draft_plan(
			label="T038 Good Relationship",
			effective_from=add_days(nowdate(), 140),
			previous_plan=base.name,
			plan_version=base.plan_version + 1,
		)
		good.plan_status = "Active"
		good.save(ignore_permissions=True)
		base.reload()
		self.assertEqual(base.replacement_plan, good.name)
		good.previous_plan = ""
		with self.assertRaisesRegex(frappe.ValidationError, "predecessor|approval and version"):
			good.save(ignore_permissions=True)

	def test_r3_t039_serialized_flags_cannot_authorize_direct_supersession(self):
		plan = self._active_plan(label="T039 Source", effective_from=add_days(nowdate(), 145))
		target = self._draft_plan(label="T039 Target", effective_from=add_days(nowdate(), 146))
		payload = json.loads(frappe.as_json(plan.as_dict()))
		payload["flags"] = {"authoritative_replacement_supersession": True}
		payload["plan_status"] = "Superseded"
		payload["replacement_plan"] = target.name
		with self.assertRaisesRegex(frappe.ValidationError, "superseded by an approved replacement"):
			frappe.get_doc(json.loads(json.dumps(payload))).save(ignore_permissions=True)
		plan.reload()
		self.assertEqual(plan.plan_status, "Active")
		self.assertFalse(plan.replacement_plan)

	def test_r3_t040_authority_marker_is_cleared_after_success_and_failure(self):
		from care_management.care_management.doctype.medication_administration_log import medication_administration_log as log_module

		plan = self._active_plan(label="T040 Source", effective_from=add_days(nowdate(), 150))
		self.assertNotIn(id(plan), log_module._AUTHORITATIVE_SUPERSESSION_DOCUMENTS)
		replacement = self._draft_plan(
			label="T040 Success",
			effective_from=add_days(nowdate(), 151),
			previous_plan=plan.name,
			plan_version=plan.plan_version + 1,
		)
		replacement.plan_status = "Active"
		replacement.save(ignore_permissions=True)
		self.assertFalse(log_module._AUTHORITATIVE_SUPERSESSION_DOCUMENTS)
		failing_base = self._active_plan(
			participant=self.participant_b,
			label="T040 Failure Source",
			effective_from=add_days(nowdate(), 160),
		)
		failing = self._draft_plan(
			participant=self.participant_b,
			label="T040 Failure",
			effective_from=add_days(nowdate(), 161),
			previous_plan=failing_base.name,
			plan_version=failing_base.plan_version + 1,
		)
		failing.plan_status = "Active"
		frappe.db.savepoint("r3_t040_authority_failure")
		original_supersede = log_module.MedicationAdministrationLog._supersede_previous_plan

		def fail_after_previous_persisted(doc):
			original_supersede(doc)
			persisted_previous = frappe.get_doc("Medication Administration Log", failing_base.name)
			self.assertEqual(persisted_previous.plan_status, "Superseded")
			self.assertEqual(persisted_previous.replacement_plan, failing.name)
			raise RuntimeError("synthetic post-predecessor-save failure")

		try:
			with patch.object(log_module.MedicationAdministrationLog, "_supersede_previous_plan", fail_after_previous_persisted):
				with self.assertRaisesRegex(RuntimeError, "post-predecessor-save"):
					failing.save(ignore_permissions=True)
			self.assertFalse(log_module._AUTHORITATIVE_SUPERSESSION_DOCUMENTS)
		finally:
			frappe.db.rollback(save_point="r3_t040_authority_failure")
		failing_base.reload()
		failing.reload()
		self.assertEqual(failing_base.plan_status, "Active")
		self.assertFalse(failing_base.replacement_plan)
		self.assertEqual(failing.plan_status, "Draft")
		self.assertEqual(failing.previous_plan, failing_base.name)
		self.assertEqual(failing.plan_version, failing_base.plan_version + 1)

	def test_r3_t041_failed_replacement_does_not_persist_partial_lifecycle_state(self):
		plan = self._active_plan(label="T041 Source", effective_from=add_days(nowdate(), 170))
		replacement = self._draft_plan(
			label="T041 Failure",
			effective_from=add_days(nowdate(), 171),
			previous_plan=plan.name,
			plan_version=plan.plan_version + 1,
		)
		replacement.plan_status = "Active"
		from care_management.care_management.doctype.medication_administration_log import medication_administration_log as log_module

		frappe.db.savepoint("r3_t041_failed_replacement")
		original_supersede = log_module.MedicationAdministrationLog._supersede_previous_plan

		def fail_after_previous_persisted(doc):
			original_supersede(doc)
			persisted_previous = frappe.get_doc("Medication Administration Log", plan.name)
			self.assertEqual(persisted_previous.plan_status, "Superseded")
			raise RuntimeError("synthetic post-predecessor-save failure")

		try:
			with patch.object(log_module.MedicationAdministrationLog, "_supersede_previous_plan", fail_after_previous_persisted):
				with self.assertRaisesRegex(RuntimeError, "post-predecessor-save"):
					replacement.save(ignore_permissions=True)
			self.assertFalse(log_module._AUTHORITATIVE_SUPERSESSION_DOCUMENTS)
		finally:
			frappe.db.rollback(save_point="r3_t041_failed_replacement")
			plan.reload()
			replacement.reload()
			self.assertEqual(plan.plan_status, "Active")
			self.assertFalse(plan.replacement_plan)
			self.assertEqual(replacement.plan_status, "Draft")
			self.assertEqual(replacement.previous_plan, plan.name)
			self.assertEqual(replacement.plan_version, plan.plan_version + 1)

	def test_r3_t042_active_replacement_round_trips_with_superseded_and_archived_predecessors(self):
		base = self._active_plan(label="T042 Source", effective_from=add_days(nowdate(), 180))
		replacement = self._draft_plan(
			label="T042 Replacement",
			effective_from=add_days(nowdate(), 181),
			previous_plan=base.name,
			plan_version=base.plan_version + 1,
		)
		replacement.plan_status = "Active"
		replacement.save(ignore_permissions=True)
		for status in ("Superseded", "Archived"):
			base.reload()
			if status == "Archived":
				base.plan_status = "Archived"
				base.lifecycle_reason = f"{RUN_PREFIX} T042 archive"
				base.save(ignore_permissions=True)
			payload = json.loads(frappe.as_json(frappe.get_doc("Medication Administration Log", replacement.name).as_dict()))
			round_tripped = frappe.get_doc(json.loads(json.dumps(payload)))
			round_tripped.save(ignore_permissions=True)
			base.reload()
			round_tripped.reload()
			self.assertEqual(base.plan_status, status)
			self.assertEqual(base.replacement_plan, replacement.name)
			self.assertEqual(round_tripped.previous_plan, base.name)

	def test_r3_t043_effective_period_and_typed_history_round_trips_are_exact(self):
		for offset, label, effective_to in ((220, "Populated", add_days(nowdate(), 240)), (260, "Absent", None)):
			plan, event, _, _ = self._selected_days_plan_with_event(f"T043 {label}", scheduled_date=add_days(nowdate(), offset))
			if effective_to:
				frappe.db.set_value("Medication Administration Log", plan.name, "effective_to", effective_to, update_modified=False)
				plan.reload()
			payload = json.loads(frappe.as_json(plan.as_dict()))
			payload["approved_on"] = str(plan.approved_on)
			payload["medication_items"][0]["scheduled_time"] = "08:00:00"
			frappe.get_doc(json.loads(json.dumps(payload))).save(ignore_permissions=True)
			plan.reload()
			event.reload()
			self.assertEqual(plan.effective_to, frappe.utils.getdate(effective_to) if effective_to else None)
			self.assertEqual(event.medication_plan, plan.name)
			child = frappe.get_doc("Medication Plan Item", plan.medication_items[0].name)
			child.scheduled_time = "08:00:01"
			with self.assertRaisesRegex(frappe.ValidationError, "materially changed"):
				child.save(ignore_permissions=True)

	def test_r3_t044_protected_field_regressions_are_independent_of_production_tuple(self):
		expected_fields = {
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
			"monday",
			"tuesday",
			"wednesday",
			"thursday",
			"friday",
			"saturday",
			"sunday",
			"instructions",
			"storage_instructions",
			"side_effects",
			"escalation_instructions",
		}
		self.assertTrue(expected_fields.issubset(set(PROTECTED_HISTORY_FIELDS)))
		plan, event, _, _ = self._selected_days_plan_with_event("T044")
		valid_changes = {
			"medication_name": "Changed Medication",
			"dosage": "20 mg",
			"route": "Topical",
			"time_slot": "12 PM (Lunch)",
			"medication_form": "Liquid",
			"strength": "20 mg",
			"prescribed_dose": "20",
			"dose_unit": "ml",
			"scheduled_time": "09:00:00",
			"frequency": "Daily",
			"indication": "Changed indication",
			"is_prn": 1,
			"is_controlled_drug": 1,
			"is_active": 0,
			"prn_indication": "Changed PRN",
			"prn_minimum_interval_hours": 4,
			"prn_maximum_dose": "40",
			"monday": 0,
			"tuesday": 0,
			"wednesday": 0,
			"thursday": 0,
			"friday": 0,
			"saturday": 0,
			"sunday": 0,
			"instructions": "Changed instructions",
			"storage_instructions": "Changed storage",
			"side_effects": "Changed side effects",
			"escalation_instructions": "Changed escalation",
		}
		for fieldname in sorted(expected_fields):
			child = frappe.get_doc("Medication Plan Item", plan.medication_items[0].name)
			original = child.get(fieldname)
			new_value = valid_changes[fieldname]
			if fieldname in {"is_prn", "is_controlled_drug", "is_active", *("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}:
				new_value = 0 if int(original or 0) else 1
			self.assertNotEqual(original, new_value, fieldname)
			child.set(fieldname, new_value)
			with self.subTest(fieldname=fieldname), self.assertRaisesRegex(frappe.ValidationError, "materially changed"):
				child.save(ignore_permissions=True)
			child.reload()
			event.reload()
			self.assertEqual(child.get(fieldname), original)
			self.assertEqual(event.medication_plan_item, child.name)

	def test_r3_t045_docstatus_shaped_inputs_cannot_bypass_finalization_controls(self):
		plan = self._active_plan(label="T045", effective_from=add_days(nowdate(), 230))
		self._competency(valid_from=add_days(nowdate(), 229), expiry_date=add_days(nowdate(), 260))
		payload = self._event(plan=plan, scheduled_datetime=f"{add_days(nowdate(), 230)} 08:00:00").as_dict()
		payload["docstatus"] = 1
		payload["finalized_by"] = self.worker_b
		payload["finalized_on"] = "2000-01-01 00:00:00"
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(json.loads(json.dumps(payload))).insert(ignore_permissions=True)
		self.assertFalse(frappe.db.exists("Medication Administration Event", {"finalized_by": self.worker_b}))
		payload["docstatus"] = 0
		shaped = frappe.get_doc(json.loads(json.dumps(payload))).insert(ignore_permissions=True)
		self.assertEqual(shaped.docstatus, 0)
		self.assertFalse(shaped.finalized_by)
		with self._as_user(self.worker):
			shaped.submit()
		self.assertEqual(shaped.finalized_by, self.worker)
		self.assertNotEqual(str(shaped.finalized_on), "2000-01-01 00:00:00")

	def test_r3_t046_disabled_named_worker_gate_is_not_masked_by_other_prerequisites(self):
		plan = self._active_plan(label="T046", effective_from=add_days(nowdate(), 240))
		self._competency(valid_from=add_days(nowdate(), 239), expiry_date=add_days(nowdate(), 260))
		task = self._medication_task(plan, self.worker, "T046")
		frappe.db.set_value("User", self.worker, "enabled", 0, update_modified=False)
		frappe.clear_cache(user=self.worker)
		event = self._event(plan=plan, task=task, scheduled_datetime=f"{add_days(nowdate(), 240)} 08:00:00").insert(
			ignore_permissions=True
		)
		event.administrative_override_reason = "Audited disabled-worker proof"
		with self._as_user("Administrator"), self.assertRaises(frappe.PermissionError):
			event.submit()

	def test_r3_t047_assignment_denial_is_isolated_and_then_permitted(self):
		plan = self._active_plan(label="T047", effective_from=add_days(nowdate(), 250))
		self._competency(valid_from=add_days(nowdate(), 249), expiry_date=add_days(nowdate(), 270))
		task = self._support_task(self.support_plan, "T047 Missing", None, source_doc=plan, source_row_id=plan.medication_items[0].name)
		denied = self._event(plan=plan, task=task, scheduled_datetime=f"{add_days(nowdate(), 250)} 08:00:00").insert(
			ignore_permissions=True
		)
		with self._as_user(self.worker), self.assertRaises(frappe.PermissionError):
			denied.submit()
		task_doc = frappe.get_doc("Support Task", task)
		task_doc.append("assigned_staff_table", {"staff_user": self.worker, "role": "Primary Carer"})
		task_doc.save(ignore_permissions=True)
		allowed = self._event(plan=plan, task=task, scheduled_datetime=f"{add_days(nowdate(), 251)} 08:00:00").insert(
			ignore_permissions=True
		)
		with self._as_user(self.worker):
			allowed.submit()
		self.assertEqual(allowed.finalized_by, self.worker)

	def test_r3_t048_execution_instance_context_is_authoritative(self):
		execution_meta = frappe.get_meta("Support Task Execution Instance")
		self.assertFalse(execution_meta.has_field("participant"))
		plan = self._active_plan(label="T048", effective_from=add_days(nowdate(), 260))
		self._competency(valid_from=add_days(nowdate(), 259), expiry_date=add_days(nowdate(), 280))
		task = self._medication_task(plan, self.worker, "T048")
		execution = self._execution_instance(task, scheduled_date=add_days(nowdate(), 260))
		event = self._event(
			plan=plan,
			task=task,
			scheduled_datetime=f"{add_days(nowdate(), 260)} 08:00:00",
		)
		event.execution_instance = execution
		event.insert(ignore_permissions=True)
		wrong_task = self._medication_task(plan, self.worker, "T048 Wrong Task")
		bad = self._event(plan=plan, task=wrong_task, scheduled_datetime=f"{add_days(nowdate(), 261)} 08:00:00")
		bad.execution_instance = execution
		with self.assertRaisesRegex(frappe.ValidationError, "Execution instance"):
			bad.insert(ignore_permissions=True)
		wrong_date = self._event(plan=plan, task=task, scheduled_datetime=f"{add_days(nowdate(), 261)} 08:00:00")
		wrong_date.execution_instance = execution
		with self.assertRaisesRegex(frappe.ValidationError, "scheduled occurrence"):
			wrong_date.insert(ignore_permissions=True)
		frappe.db.set_value("Support Task Execution Instance", execution, "scheduled_time", None, update_modified=False)
		bad_missing = self._event(plan=plan, task=task, scheduled_datetime=f"{add_days(nowdate(), 260)} 08:00:00")
		bad_missing.execution_instance = execution
		with self.assertRaisesRegex(frappe.ValidationError, "lacks an authoritative"):
			bad_missing.insert(ignore_permissions=True)

	def test_r3_t049_effective_period_boundaries_are_inclusive_and_outside_denied(self):
		start = add_days(nowdate(), 290)
		end = add_days(nowdate(), 292)
		plan = self._active_plan(label="T049", effective_from=start)
		plan.effective_to = end
		plan.save(ignore_permissions=True)
		self._competency(valid_from=add_days(start, -1), expiry_date=add_days(end, 1))
		for offset in (0, 2):
			event = self._event(plan=plan, scheduled_datetime=f"{add_days(start, offset)} 08:00:00")
			event.insert(ignore_permissions=True)
		for when in (add_days(start, -1), add_days(end, 1)):
			event = self._event(plan=plan, scheduled_datetime=f"{when} 08:00:00")
			with self.subTest(when=when), self.assertRaisesRegex(frappe.ValidationError, "outside"):
				event.insert(ignore_permissions=True)
