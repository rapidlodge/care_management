from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime, today

from care_management.care_management import permissions
from care_management.care_management.doctype.controlled_medication_transaction.controlled_medication_transaction import (
	create_source_transaction,
	latest_balance,
	source_key,
)
from care_management.care_management.doctype.medication_administration_event.medication_administration_event import (
	prn_review_is_overdue,
	prn_review_is_satisfied,
)
from care_management.care_management.tests.helpers import (
	ensure_r2c1_participant,
	ensure_r2c1_support_plan,
	ensure_r2c1_support_task,
	ensure_r2c1_task_assignment,
	ensure_r2c1_user,
	ensure_r2c1_user_permission,
)


@contextmanager
def acting_as(user):
	previous = frappe.session.user
	frappe.set_user(user)
	try:
		yield
	finally:
		frappe.set_user(previous)


class TestMedicationR3C2SafeguardContract(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.participant_a = ensure_r2c1_participant("R3C2 A", "6234567890")
		self.participant_b = ensure_r2c1_participant("R3C2 B", "62345678901")
		self.worker = ensure_r2c1_user("R3C2 Worker", ["Support Worker"])
		self.worker_b = ensure_r2c1_user("R3C2 Worker B", ["Support Worker"])
		self.care_manager = ensure_r2c1_user("R3C2 Care Manager", ["Care Manager"])
		self.coordinator = ensure_r2c1_user("R3C2 Coordinator", ["Support Coordinator"])
		self.system_manager = ensure_r2c1_user("R3C2 System Manager", ["System Manager"])
		for doctype in (
			"Medication Administration Event",
			"Medication PRN Effectiveness Review",
			"Participant Drug Count",
			"Shift Medication Check",
			"Discarded Medication Register",
			"Incident",
			"Controlled Medication Transaction",
		):
			ensure_r2c1_user_permission(self.worker, self.participant_a, applicable_for=doctype)
			ensure_r2c1_user_permission(self.care_manager, self.participant_a, applicable_for=doctype)
			ensure_r2c1_user_permission(self.coordinator, self.participant_a, applicable_for=doctype)
		ensure_r2c1_user_permission(self.worker_b, self.participant_b, applicable_for="Medication Administration Event")
		self.support_plan = ensure_r2c1_support_plan(self.participant_a, "R3C2 A")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def make_competency(self, worker=None, competency_type="General Medication", active=True):
		valid_from = today() if active else add_to_date(today(), days=-30)
		expiry_date = add_to_date(today(), days=30) if active else add_to_date(today(), days=-1)
		return frappe.get_doc(
			{
				"doctype": "Medication Competency",
				"worker": worker or self.worker,
				"competency_type": competency_type,
				"status": "Active" if active else "Expired",
				"is_active": 1 if active else 0,
				"valid_from": valid_from,
				"expiry_date": expiry_date,
				"assessed_by": self.care_manager,
				"assessed_on": today(),
			}
		).insert(ignore_permissions=True)

	def make_plan(self, updates=None, participant=None):
		item = {
			"medication_name": "R3C2 Medication",
			"prescribed_dose": "1",
			"dose_unit": "tablet",
			"route": "Oral",
			"time_slot": "8 AM",
			"scheduled_time": "08:00:00",
			"frequency": "Daily",
			"indication": "Routine support",
			"is_active": 1,
			"monday": 1,
			"tuesday": 1,
			"wednesday": 1,
			"thursday": 1,
			"friday": 1,
			"saturday": 1,
			"sunday": 1,
		}
		item.update(updates or {})
		plan = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": participant or self.participant_a,
				"week_commencing": today(),
				"plan_status": "Draft",
				"plan_version": 1,
				"effective_from": today(),
				"review_date": add_to_date(today(), days=30),
				"purpose_evidence_status": "Recorded",
				"change_reason": "R3C2 plan",
				"medication_items": [item],
			}
		).insert(ignore_permissions=True)
		plan.plan_status = "Active"
		plan.save(ignore_permissions=True)
		return plan

	def make_incident(self, incident_type="Medication Error", participant=None, reporter=None):
		return frappe.get_doc(
			{
				"doctype": "Incident",
				"participant": participant or self.participant_a,
				"reported_by": reporter or self.worker,
				"time_of_incident": "08:00:00",
				"date_of_incident": today(),
				"location_of_incident": "R3C2 location",
				"incident_type": incident_type,
				"was_rp_used": "No",
				"full_description_of_incident": "R3C2 synthetic report",
				"severity": "Low",
			}
		).insert(ignore_permissions=True)

	def make_submitted_prn_review(self, event, notes="settled"):
		review = frappe.get_doc(
			{
				"doctype": "Medication PRN Effectiveness Review",
				"participant": event.participant,
				"medication_event": event.name,
				"reviewed_at": now_datetime(),
				"effectiveness_outcome": "Effective",
				"effectiveness_notes": notes,
			}
		)
		with acting_as(self.care_manager):
			review.insert()
			review.submit()
		return review

	def make_event(self, plan, outcome="Administered", dose="1", **overrides):
		item = plan.medication_items[0]
		worker = overrides.get("worker", self.worker)
		values = {
			"doctype": "Medication Administration Event",
			"participant": plan.participant,
			"medication_plan": plan.name,
			"medication_plan_item": item.name,
			"scheduled_datetime": f"{today()} 08:00:00",
			"actual_datetime": f"{today()} 08:00:00",
			"worker": worker,
			"support_task": None if item.get("is_prn") else self.medication_task(plan, worker=worker),
			"outcome": outcome,
			"administered_dose": dose,
			"variance_reason": "variance" if outcome != "Administered" else None,
		}
		values.update(overrides)
		return frappe.get_doc(values)

	def medication_task(self, plan, worker=None):
		item = plan.medication_items[0]
		support_plan = ensure_r2c1_support_plan(plan.participant, f"R3C2 Medication {plan.name}")
		task_name = ensure_r2c1_support_task(support_plan, f"R3C2 Medication {plan.name} {item.name}")
		task = frappe.get_doc("Support Task", task_name)
		task.task_category = "Medication"
		task.status = "Active"
		task.source_doctype = "Medication Administration Log"
		task.source_docname = plan.name
		task.source_row_id = item.name
		if not task.schedule_rules:
			task.append(
				"schedule_rules",
				{
					"scheduled_time": "08:00:00",
					"recurrence_type": "Daily",
					"start_date": today(),
					"is_floating": 0,
				},
			)
		for row in task.schedule_rules:
			row.scheduled_time = "08:00:00"
			row.recurrence_type = "Daily"
			row.start_date = today()
			row.is_floating = 0
		task.save(ignore_permissions=True)
		ensure_r2c1_task_assignment(task.name, worker or self.worker)
		return task.name

	def grant_competencies(self, *types):
		for competency_type in types or ("General Medication",):
			self.make_competency(competency_type=competency_type)

	def submit_event(self, event):
		with acting_as(event.worker):
			event.insert()
			self.assertFalse(event.flags.get("ignore_permissions"))
			event.submit()
		return event

	def prn_plan(self):
		return self.make_plan(
			{
				"is_prn": 1,
				"prn_indication": "pain",
				"prn_minimum_interval_hours": 4,
				"prn_maximum_dose": "2",
				"prn_review_due_minutes": 60,
			}
		)

	def controlled_plan(self):
		return self.make_plan({"is_controlled_drug": 1})

	def make_opening_balance(self, plan, quantity="10"):
		item = plan.medication_items[0]
		doc = frappe.get_doc(
			{
				"doctype": "Controlled Medication Transaction",
				"participant": plan.participant,
				"medication_plan": plan.name,
				"medication_plan_item": item.name,
				"posting_datetime": now_datetime(),
				"transaction_type": "Opening Balance",
				"quantity": quantity,
				"dose_unit": item.dose_unit,
				"witness": self.system_manager,
			}
		)
		with acting_as(self.care_manager):
			doc.insert()
			doc.submit()
		return doc

	def test_prn_item_is_not_auto_scheduled(self):
		plan = self.prn_plan()
		self.assertFalse(
			frappe.db.exists("Support Task", {"source_docname": plan.name, "source_row_id": plan.medication_items[0].name})
		)

	def test_valid_prn_administration_uses_explicit_actual_time(self):
		self.grant_competencies("General Medication", "PRN Medication")
		plan = self.prn_plan()
		with self.assertRaises(frappe.ValidationError):
			self.make_event(plan, actual_datetime=None, scheduled_datetime=None).insert()
		event = self.submit_event(self.make_event(plan))
		self.assertEqual(event.scheduled_datetime, event.actual_datetime)

	def test_prn_activation_requires_indication_interval_maximum_and_review_due(self):
		for missing in ("prn_indication", "prn_minimum_interval_hours", "prn_maximum_dose", "prn_review_due_minutes"):
			values = {"is_prn": 1, "prn_indication": "pain", "prn_minimum_interval_hours": 4, "prn_maximum_dose": "2", "prn_review_due_minutes": 60}
			values[missing] = None
			with self.assertRaises(frappe.ValidationError):
				self.make_plan(values)

	def test_prn_review_due_minutes_must_be_positive(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_plan({"is_prn": 1, "prn_indication": "pain", "prn_minimum_interval_hours": 4, "prn_maximum_dose": "2", "prn_review_due_minutes": 0})

	def test_prn_minimum_interval_uses_latest_submitted_administered_event(self):
		self.grant_competencies("General Medication", "PRN Medication")
		plan = self.prn_plan()
		self.submit_event(self.make_event(plan, actual_datetime=f"{today()} 08:00:00", scheduled_datetime=f"{today()} 08:00:00"))
		second = self.make_event(plan, actual_datetime=f"{today()} 10:00:00", scheduled_datetime=f"{today()} 10:00:00")
		call_order = []
		real_sql = frappe.db.sql
		real_get_all = frappe.get_all

		def ordered_sql(query, *args, **kwargs):
			if "tabMedication Plan Item" in query and "for update" in query.lower():
				call_order.append("plan_item_lock")
			return real_sql(query, *args, **kwargs)

		def ordered_get_all(doctype, *args, **kwargs):
			if doctype == "Medication Administration Event":
				call_order.append("latest_prn_event_query")
			return real_get_all(doctype, *args, **kwargs)

		with patch("frappe.db.sql", side_effect=ordered_sql), patch("frappe.get_all", side_effect=ordered_get_all):
			with self.assertRaises(frappe.ValidationError):
				second.insert()
		self.assertEqual(call_order[:2], ["plan_item_lock", "latest_prn_event_query"])
		self.assertEqual(
			frappe.db.count(
				"Medication Administration Event",
				{"participant": self.participant_a, "medication_plan_item": plan.medication_items[0].name, "outcome": "Administered", "docstatus": 1},
			),
			1,
		)

	def test_prn_non_administered_outcomes_do_not_reset_interval(self):
		self.grant_competencies("General Medication", "PRN Medication")
		plan = self.prn_plan()
		self.submit_event(self.make_event(plan, outcome="Refused", actual_datetime=f"{today()} 08:00:00", scheduled_datetime=f"{today()} 08:00:00"))
		permitted_time = f"{today()} 09:00:00"
		event = self.make_event(plan, actual_datetime=permitted_time, scheduled_datetime=permitted_time).insert()
		self.assertTrue(event.name)
		self.assertEqual(event.docstatus, 0)
		self.assertEqual(str(event.actual_datetime), permitted_time)

	def test_prn_maximum_dose_is_per_administration_ceiling(self):
		plan = self.prn_plan()
		with self.assertRaises(frappe.ValidationError):
			self.make_event(plan, dose="3").insert()

	def test_prn_dose_comparison_requires_decimal_values(self):
		plan = self.prn_plan()
		with self.assertRaises(frappe.ValidationError):
			self.make_event(plan, dose="not-a-number").insert()

	def test_prn_dose_unit_must_match_plan_item(self):
		plan = self.prn_plan()
		item = plan.medication_items[0]
		conflicting_unit = "ml"
		self.assertNotEqual(item.dose_unit, conflicting_unit)
		event = self.make_event(plan, dose_unit=conflicting_unit).insert()
		self.assertEqual(event.dose_unit, item.dose_unit)
		self.assertNotEqual(event.dose_unit, conflicting_unit)

	def test_prn_indication_is_snapshotted_from_plan_item(self):
		event = self.make_event(self.prn_plan()).insert()
		self.assertEqual(event.prn_indication, "pain")

	def test_prn_event_stores_review_due_at_without_review_status(self):
		self.grant_competencies("General Medication", "PRN Medication")
		event = self.submit_event(self.make_event(self.prn_plan()))
		self.assertTrue(event.prn_review_due_at)
		self.assertFalse(frappe.get_meta("Medication Administration Event").has_field("prn_" + "review_status"))
		evaluation_time = add_to_date(event.prn_review_due_at, seconds=1, as_datetime=True)
		self.assertFalse(prn_review_is_satisfied(event.name, user=self.care_manager))
		self.assertTrue(prn_review_is_overdue(event.name, user=self.care_manager, now=evaluation_time))
		self.make_submitted_prn_review(event)
		self.assertTrue(prn_review_is_satisfied(event.name, user=self.care_manager))
		self.assertFalse(prn_review_is_overdue(event.name, user=self.care_manager, now=evaluation_time))

	def test_one_submitted_prn_effectiveness_review_per_event(self):
		self.grant_competencies("General Medication", "PRN Medication")
		event = self.submit_event(self.make_event(self.prn_plan()))
		with patch("frappe.db.sql", wraps=frappe.db.sql) as sql:
			review = self.make_submitted_prn_review(event)
		self.assertTrue(any("tabMedication Administration Event" in call.args[0] and "for update" in call.args[0].lower() for call in sql.call_args_list))
		duplicate = frappe.get_doc(
			{
				"doctype": "Medication PRN Effectiveness Review",
				"participant": self.participant_a,
				"medication_event": event.name,
				"reviewed_at": now_datetime(),
				"effectiveness_outcome": "Effective",
				"effectiveness_notes": "second review",
			}
		)
		with acting_as(self.care_manager):
			duplicate.insert()
			self.assertEqual(duplicate.docstatus, 0)
			with patch("frappe.db.sql", wraps=frappe.db.sql) as duplicate_sql:
				with self.assertRaises(frappe.ValidationError) as captured:
					duplicate.submit()
			self.assertIn("Only one submitted PRN effectiveness review is allowed per medication event.", str(captured.exception))
		self.assertTrue(any("tabMedication Administration Event" in call.args[0] and "for update" in call.args[0].lower() for call in duplicate_sql.call_args_list))
		self.assertEqual(frappe.db.count("Medication PRN Effectiveness Review", {"medication_event": event.name, "docstatus": 1}), 1)

	def test_administering_worker_can_edit_own_draft_review(self):
		self.grant_competencies("General Medication", "PRN Medication")
		event = self.submit_event(self.make_event(self.prn_plan()))
		with acting_as(self.worker):
			review = frappe.get_doc({"doctype": "Medication PRN Effectiveness Review", "participant": self.participant_a, "medication_event": event.name, "reviewed_at": now_datetime(), "effectiveness_outcome": "Effective", "effectiveness_notes": "settled"}).insert()
			review.effectiveness_notes = "still settled"
			review.save()
			reloaded = frappe.get_doc("Medication PRN Effectiveness Review", review.name)
			self.assertEqual(reloaded.effectiveness_notes, "still settled")
			self.assertEqual(reloaded.docstatus, 0)
			self.assertEqual(reloaded.administering_worker, self.worker)

	def test_only_care_manager_or_system_manager_can_submit_prn_review(self):
		self.grant_competencies("General Medication", "PRN Medication")
		event = self.submit_event(self.make_event(self.prn_plan()))
		with acting_as(self.worker):
			review = frappe.get_doc({"doctype": "Medication PRN Effectiveness Review", "participant": self.participant_a, "medication_event": event.name, "reviewed_at": now_datetime(), "effectiveness_outcome": "Effective", "effectiveness_notes": "settled"}).insert()
			with self.assertRaises(frappe.PermissionError):
				review.submit()

	def test_submitted_prn_review_is_immutable(self):
		self.grant_competencies("General Medication", "PRN Medication")
		event = self.submit_event(self.make_event(self.prn_plan()))
		with acting_as(self.care_manager):
			review = frappe.get_doc({"doctype": "Medication PRN Effectiveness Review", "participant": self.participant_a, "medication_event": event.name, "reviewed_at": now_datetime(), "effectiveness_outcome": "Effective", "effectiveness_notes": "settled"}).insert()
			review.submit()
			review.effectiveness_notes = "changed"
			with self.assertRaises(frappe.ValidationError):
				review.save()

	def test_adverse_reaction_review_requires_same_participant_incident(self):
		self.grant_competencies("General Medication", "PRN Medication")
		event = self.submit_event(self.make_event(self.prn_plan()))
		cross_incident = self.make_incident("Adverse Medication Reaction", participant=self.participant_b)
		with acting_as(self.care_manager):
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc({"doctype": "Medication PRN Effectiveness Review", "participant": self.participant_a, "medication_event": event.name, "reviewed_at": now_datetime(), "effectiveness_outcome": "Adverse Reaction", "effectiveness_notes": "rash"}).insert()
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc({"doctype": "Medication PRN Effectiveness Review", "participant": self.participant_a, "medication_event": event.name, "reviewed_at": now_datetime(), "effectiveness_outcome": "Adverse Reaction", "effectiveness_notes": "rash", "incident": cross_incident.name}).insert()
			incident = self.make_incident("Adverse Medication Reaction")
			frappe.get_doc({"doctype": "Medication PRN Effectiveness Review", "participant": self.participant_a, "medication_event": event.name, "reviewed_at": now_datetime(), "effectiveness_outcome": "Adverse Reaction", "effectiveness_notes": "rash", "incident": incident.name}).insert()

	def test_general_competency_required_for_every_administration(self):
		with self.assertRaises(frappe.PermissionError):
			self.submit_event(self.make_event(self.make_plan()))

	def test_prn_competency_required_for_prn_administration(self):
		self.make_competency(competency_type="General Medication")
		with self.assertRaises(frappe.PermissionError):
			self.submit_event(self.make_event(self.prn_plan()))

	def test_controlled_competency_required_for_controlled_administration(self):
		self.make_competency(competency_type="General Medication")
		with self.assertRaises(frappe.PermissionError):
			self.submit_event(self.make_event(self.controlled_plan(), checker=self.care_manager))

	def test_topical_route_requires_topical_competency(self):
		self.grant_competencies("General Medication")
		with self.assertRaises(frappe.PermissionError):
			self.submit_event(self.make_event(self.make_plan({"route": "Topical"})))

	def test_injection_route_requires_injection_competency(self):
		self.grant_competencies("General Medication")
		with self.assertRaises(frappe.PermissionError):
			self.submit_event(self.make_event(self.make_plan({"route": "Injection"})))

	def test_inhaled_route_requires_inhaled_competency(self):
		self.grant_competencies("General Medication")
		with self.assertRaises(frappe.PermissionError):
			self.submit_event(self.make_event(self.make_plan({"route": "Inhaled"})))

	def test_other_route_fails_activation(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_plan({"route": "Other"})

	def test_competency_checked_on_actual_administration_date(self):
		self.make_competency(active=False)
		with self.assertRaises(frappe.PermissionError):
			self.submit_event(self.make_event(self.make_plan()))

	def test_administrative_handling_does_not_bypass_worker_competency(self):
		event = self.make_event(self.make_plan(), administrative_override_reason="reviewed")
		with acting_as(self.system_manager):
			event.insert(ignore_permissions=True)
			with self.assertRaises(frappe.PermissionError):
				event.submit()

	def test_opening_balance_requires_no_prior_transaction_and_distinct_witness(self):
		plan = self.controlled_plan()
		item = plan.medication_items[0]
		doc = frappe.get_doc({"doctype": "Controlled Medication Transaction", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "posting_datetime": now_datetime(), "transaction_type": "Opening Balance", "direction": "Increase", "quantity": "5", "dose_unit": item.dose_unit, "balance_before": "0", "balance_after": "5", "actor": self.care_manager, "witness": self.care_manager, "source_doctype": "Controlled Medication Transaction", "source_docname": "manual", "source_action": "Opening Balance"})
		with acting_as(self.care_manager):
			with self.assertRaises(frappe.PermissionError):
				doc.insert()
		opening = self.make_opening_balance(plan, "5")
		reversal_incident = self.make_incident()
		correction = frappe.get_doc({"doctype": "Controlled Medication Transaction", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "posting_datetime": now_datetime(), "transaction_type": "Correction Decrease", "quantity": "5", "dose_unit": item.dose_unit, "witness": self.system_manager, "source_doctype": "Controlled Medication Transaction", "source_docname": "manual-correction", "source_action": "Correction Decrease", "reason": "stock correction", "incident": reversal_incident.name, "reverses_transaction": opening.name})
		with acting_as(self.care_manager):
			correction.insert()
			correction.submit()
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc({"doctype": "Controlled Medication Transaction", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "transaction_type": "Opening Balance", "quantity": "1", "dose_unit": item.dose_unit, "witness": self.system_manager}).insert()

	def test_controlled_administered_event_creates_one_transaction(self):
		self.grant_competencies("General Medication", "Controlled Medication")
		plan = self.controlled_plan()
		self.make_opening_balance(plan, "5")
		event = self.submit_event(self.make_event(plan, checker=self.care_manager))
		self.assertEqual(event.docstatus, 1)
		rows = frappe.get_all(
			"Controlled Medication Transaction",
			filters={"source_docname": event.name, "docstatus": 1},
			fields=["transaction_type", "actor", "finalized_by", "source_doctype", "source_action", "quantity", "balance_before", "balance_after"],
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].transaction_type, "Administration")
		self.assertEqual(rows[0].actor, self.worker)
		self.assertEqual(rows[0].finalized_by, self.worker)
		self.assertEqual(rows[0].source_doctype, "Medication Administration Event")
		self.assertEqual(rows[0].source_action, "Administration")
		self.assertEqual(Decimal(str(rows[0].quantity)), Decimal("1"))
		self.assertEqual(Decimal(str(rows[0].balance_before)), Decimal("5"))
		self.assertEqual(Decimal(str(rows[0].balance_after)), Decimal("4"))
		self.assertEqual(latest_balance(self.participant_a, plan.medication_items[0].name), Decimal("4"))
		admin_event = self.make_event(
			plan,
			checker=self.care_manager,
			actual_datetime=f"{add_to_date(today(), days=1)} 08:00:00",
			scheduled_datetime=f"{add_to_date(today(), days=1)} 08:00:00",
			administrative_override_reason="managerial override",
		)
		admin_event.actor = "Administrator"
		with acting_as("Administrator"):
			admin_event.insert()
			admin_event.submit()
		admin_row = frappe.db.get_value(
			"Controlled Medication Transaction",
			{"source_docname": admin_event.name, "docstatus": 1},
			["actor", "finalized_by"],
			as_dict=True,
		)
		self.assertEqual(admin_row.actor, self.worker)
		self.assertEqual(admin_row.finalized_by, "Administrator")

	def test_controlled_transaction_requires_direction_unit_actor_witness_and_balance(self):
		plan = self.controlled_plan()
		item = plan.medication_items[0]
		doc = frappe.get_doc({"doctype": "Controlled Medication Transaction", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "posting_datetime": now_datetime(), "transaction_type": "Opening Balance", "quantity": "5", "dose_unit": item.dose_unit, "actor": "Guest", "direction": "Decrease", "balance_before": "999", "balance_after": "998", "witness": self.system_manager, "source_doctype": "Controlled Medication Transaction", "source_docname": "manual", "source_action": "Opening Balance"})
		with acting_as(self.care_manager):
			doc.insert()
			doc.submit()
		self.assertEqual(doc.actor, self.care_manager)
		self.assertEqual(doc.direction, "Increase")
		self.assertEqual(Decimal(str(doc.balance_before)), Decimal("0"))
		self.assertEqual(Decimal(str(doc.balance_after)), Decimal("5"))
		self.assertEqual(doc.source_doctype, "Controlled Medication Transaction")
		self.assertEqual(doc.source_docname, doc.name)
		self.assertEqual(doc.source_action, "Opening Balance")
		doc.actor = "Guest"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_controlled_transaction_prevents_negative_balance(self):
		self.grant_competencies("Controlled Medication")
		plan = self.controlled_plan()
		item = plan.medication_items[0]
		self.make_opening_balance(plan, "1")
		source = frappe._dict({"doctype": "Medication Administration Event", "name": "NEGATIVE-SRC", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "actual_datetime": now_datetime(), "dose_unit": item.dose_unit, "worker": self.worker})
		with self.assertRaises(frappe.ValidationError) as captured:
			create_source_transaction(source, "Administration", "2", self.system_manager)
		self.assertIn("Controlled medication balance is invalid.", str(captured.exception))

	def test_controlled_duplicate_submission_uses_source_key_guard(self):
		self.grant_competencies("Controlled Medication")
		plan = self.controlled_plan()
		item = plan.medication_items[0]
		self.make_opening_balance(plan, "5")
		source = frappe._dict({"doctype": "Medication Administration Event", "name": "SRC-1", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "actual_datetime": now_datetime(), "dose_unit": item.dose_unit, "worker": self.worker})
		first = create_source_transaction(source, "Administration", "1", self.system_manager)
		duplicate_key = source_key(source.doctype, source.name, "Administration")
		with self.assertRaises(frappe.UniqueValidationError):
			create_source_transaction(source, "Administration", "1", self.system_manager)
		self.assertEqual(first.docstatus, 1)
		self.assertEqual(
			frappe.db.count(
				"Controlled Medication Transaction",
				{"source_key": duplicate_key, "docstatus": 1},
			),
			1,
		)

	def test_controlled_concurrent_submission_serializes_on_plan_item_lock(self):
		self.grant_competencies("Controlled Medication")
		plan = self.controlled_plan()
		item = plan.medication_items[0]
		source_a = frappe._dict({"doctype": "Medication Administration Event", "name": "SRC-A", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "actual_datetime": now_datetime(), "dose_unit": item.dose_unit, "worker": self.worker})
		source_b = frappe._dict({"doctype": "Medication Administration Event", "name": "SRC-B", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "actual_datetime": now_datetime(), "dose_unit": item.dose_unit, "worker": self.worker})
		self.make_opening_balance(plan, "10")
		draft_a = frappe.get_doc({"doctype": "Controlled Medication Transaction", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "transaction_type": "Receipt", "quantity": "1", "dose_unit": item.dose_unit, "witness": self.system_manager})
		draft_b = frappe.get_doc({"doctype": "Controlled Medication Transaction", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "transaction_type": "Receipt", "quantity": "1", "dose_unit": item.dose_unit, "witness": self.system_manager})
		with acting_as(self.care_manager):
			draft_a.insert()
			draft_b.insert()
		self.assertEqual(Decimal(str(draft_a.balance_before)), Decimal("10"))
		self.assertEqual(Decimal(str(draft_b.balance_before)), Decimal("10"))
		with acting_as(self.care_manager):
			draft_a.submit()
			draft_b.submit()
		self.assertEqual(Decimal(str(draft_a.balance_after)), Decimal("11"))
		self.assertEqual(Decimal(str(draft_b.balance_before)), Decimal("11"))
		self.assertEqual(Decimal(str(draft_b.balance_after)), Decimal("12"))
		with patch("frappe.db.sql", wraps=frappe.db.sql) as sql:
			create_source_transaction(source_a, "Administration", "1", self.system_manager)
			create_source_transaction(source_b, "Administration", "2", self.system_manager)
		self.assertTrue(any("tabMedication Plan Item" in call.args[0] and "for update" in call.args[0].lower() for call in sql.call_args_list))
		self.assertEqual(latest_balance(self.participant_a, item.name), Decimal("9"))

	def test_non_stock_outcomes_create_no_administration_transaction(self):
		self.grant_competencies("General Medication", "Controlled Medication")
		event = self.submit_event(self.make_event(self.controlled_plan(), outcome="Refused", checker=self.care_manager, variance_reason="refused"))
		self.assertEqual(frappe.db.count("Controlled Medication Transaction", {"source_docname": event.name}), 0)

	def test_correction_transaction_requires_reason_incident_and_reverses_link(self):
		plan = self.controlled_plan()
		item = plan.medication_items[0]
		reversed_txn = self.make_opening_balance(plan, "1")
		doc = frappe.get_doc({"doctype": "Controlled Medication Transaction", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "posting_datetime": now_datetime(), "transaction_type": "Correction Decrease", "quantity": "1", "dose_unit": item.dose_unit, "witness": self.system_manager, "source_doctype": "Controlled Medication Transaction", "source_docname": "manual", "source_action": "Correction Decrease", "reason": "correction", "incident": self.make_incident().name, "reverses_transaction": reversed_txn.name})
		with acting_as(self.care_manager):
			doc.insert()
			doc.submit()
			second = frappe.get_doc({"doctype": "Controlled Medication Transaction", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "posting_datetime": now_datetime(), "transaction_type": "Correction Decrease", "quantity": "1", "dose_unit": item.dose_unit, "witness": self.system_manager, "source_doctype": "Controlled Medication Transaction", "source_docname": "manual-2", "source_action": "Correction Decrease", "reason": "correction", "incident": self.make_incident().name, "reverses_transaction": reversed_txn.name})
			with self.assertRaises(frappe.ValidationError):
				second.insert()
		missing = frappe.get_doc({"doctype": "Controlled Medication Transaction", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": item.name, "posting_datetime": now_datetime(), "transaction_type": "Correction Increase", "quantity": "1", "dose_unit": item.dose_unit, "witness": self.system_manager, "source_doctype": "Controlled Medication Transaction", "source_docname": "manual", "source_action": "Correction Increase"})
		with self.assertRaises(frappe.ValidationError):
			missing.insert()

	def test_reconciliation_zero_difference_closes_reconciled(self):
		plan = self.controlled_plan()
		item = plan.medication_items[0]
		ensure_r2c1_user_permission(self.worker_b, self.participant_a, applicable_for="Participant Drug Count")
		with acting_as(self.worker):
			doc = frappe.get_doc({"doctype": "Participant Drug Count", "participant": self.participant_a, "observed_by": self.care_manager, "webster_pak_type": "Schedule 8 (S8)", "medication_plan_item": item.name, "observed_balance": "0", "drug_count_entries": [{"date": today(), "staff_name": self.worker, "expected_count": 0, "actual_count": 0, "actual_end_of_shift_count": 0, "staff_signature": self.worker}]}).insert()
		self.assertEqual(doc.observed_by, self.worker)
		stored_notes = doc.get("notes")
		with acting_as(self.worker_b):
			crafted = frappe.get_doc("Participant Drug Count", doc.name)
			crafted.observed_by = self.worker_b
			crafted.notes = "spoofed"
			self.assertFalse(frappe.has_permission("Participant Drug Count", "write", doc=crafted, user=self.worker_b))
			with self.assertRaises(frappe.PermissionError):
				crafted.save()
			self.assertNotIn(doc.name, [row.name for row in frappe.get_list("Participant Drug Count", fields=["name"])])
		doc.reload()
		self.assertEqual(doc.observed_by, self.worker)
		self.assertEqual(doc.get("notes"), stored_notes)
		with acting_as(self.care_manager):
			self.assertTrue(frappe.has_permission("Participant Drug Count", "write", doc=doc, user=self.care_manager))
			doc.submit()
		self.assertEqual(doc.reconciliation_status, "Reconciled")

	def test_reconciliation_nonzero_difference_escalates_with_incident(self):
		plan = self.controlled_plan()
		item = plan.medication_items[0]
		incident = self.make_incident()
		with acting_as(self.care_manager):
			doc = frappe.get_doc({"doctype": "Participant Drug Count", "participant": self.participant_a, "webster_pak_type": "Schedule 8 (S8)", "medication_plan_item": item.name, "observed_balance": "1", "reconciliation_status": "Escalated", "discrepancy_incident": incident.name, "drug_count_entries": [{"date": today(), "staff_name": self.worker, "expected_count": 0, "actual_count": 1, "actual_end_of_shift_count": 1, "staff_signature": self.worker}]}).insert()
			doc.submit()
		self.assertEqual(doc.reconciliation_status, "Escalated")

	def test_discrepancy_record_cannot_be_labelled_reconciled(self):
		plan = self.controlled_plan()
		item = plan.medication_items[0]
		with acting_as(self.worker):
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc({"doctype": "Participant Drug Count", "participant": self.participant_a, "webster_pak_type": "Schedule 8 (S8)", "medication_plan_item": item.name, "observed_balance": "1", "reconciliation_status": "Reconciled", "drug_count_entries": [{"date": today(), "staff_name": self.worker, "expected_count": 0, "actual_count": 1, "actual_end_of_shift_count": 1, "staff_signature": self.worker}]}).insert()

	def test_shift_medication_check_links_exact_reconciliation_only(self):
		plan = self.controlled_plan()
		item = plan.medication_items[0]
		plan_b = self.make_plan({"is_controlled_drug": 1}, participant=self.participant_b)
		item_b = plan_b.medication_items[0]
		draft = frappe.get_doc({"doctype": "Participant Drug Count", "participant": self.participant_a, "webster_pak_type": "Schedule 8 (S8)", "medication_plan_item": item.name, "observed_balance": "0", "drug_count_entries": [{"date": today(), "staff_name": self.worker, "expected_count": 0, "actual_count": 0, "actual_end_of_shift_count": 0, "staff_signature": self.worker}]}).insert(ignore_permissions=True)
		cross = frappe.get_doc({"doctype": "Participant Drug Count", "participant": self.participant_b, "webster_pak_type": "Schedule 8 (S8)", "medication_plan_item": item_b.name, "observed_balance": "0", "drug_count_entries": [{"date": today(), "staff_name": self.worker, "expected_count": 0, "actual_count": 0, "actual_end_of_shift_count": 0, "staff_signature": self.worker}]}).insert(ignore_permissions=True)
		non_exact = frappe.get_doc({"doctype": "Participant Drug Count", "participant": self.participant_a, "webster_pak_type": "Schedule 8 (S8)", "medication_plan_item": item.name, "observed_balance": "1", "reconciliation_status": "Escalated", "discrepancy_incident": self.make_incident().name, "drug_count_entries": [{"date": today(), "staff_name": self.worker, "expected_count": 0, "actual_count": 1, "actual_end_of_shift_count": 1, "staff_signature": self.worker}]}).insert(ignore_permissions=True)
		with acting_as(self.care_manager):
			non_exact.submit()
		doc = frappe.get_doc({"doctype": "Shift Medication Check", "participant": self.participant_a, "month": "January", "reconciliation": "missing", "check_entries": [{"date": today(), "staff_name_and_signature": self.worker}]})
		with acting_as(self.worker):
			with self.assertRaises(frappe.ValidationError):
				doc.insert()
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc({"doctype": "Shift Medication Check", "participant": self.participant_a, "month": "January", "reconciliation": draft.name, "check_entries": [{"date": today(), "staff_name_and_signature": self.worker}]}).insert()
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc({"doctype": "Shift Medication Check", "participant": self.participant_a, "month": "January", "reconciliation": cross.name, "check_entries": [{"date": today(), "staff_name_and_signature": self.worker}]}).insert()
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc({"doctype": "Shift Medication Check", "participant": self.participant_a, "month": "January", "reconciliation": non_exact.name, "check_entries": [{"date": today(), "staff_name_and_signature": self.worker}]}).insert()
			valid = frappe.get_doc({"doctype": "Shift Medication Check", "participant": self.participant_a, "checked_by": self.care_manager, "month": "January", "reconciliation": draft.name, "check_entries": [{"date": today(), "staff_name_and_signature": self.worker}]})
		draft.reconciliation_status = "Reconciled"
		with acting_as(self.care_manager):
			draft.submit()
		with acting_as(self.worker):
			valid.insert()
		self.assertEqual(valid.checked_by, self.worker)
		ensure_r2c1_user_permission(self.worker_b, self.participant_a, applicable_for="Shift Medication Check")
		with acting_as(self.worker_b):
			crafted = frappe.get_doc("Shift Medication Check", valid.name)
			crafted.checked_by = self.worker_b
			with self.assertRaises(frappe.PermissionError):
				crafted.save()
			self.assertNotIn(valid.name, [row.name for row in frappe.get_list("Shift Medication Check", fields=["name"])])
		valid.reload()
		self.assertEqual(valid.checked_by, self.worker)
		with acting_as(self.care_manager):
			valid.submit()

	def test_non_controlled_disposal_records_participant_plan_item_quantity_unit(self):
		plan = self.make_plan()
		item = plan.medication_items[0]
		with acting_as(self.worker):
			doc = frappe.get_doc({"doctype": "Discarded Medication Register", "participant": self.participant_a, "prepared_by": self.care_manager, "discarded_items": [{"date": today(), "medication_details": "returned", "medication_plan_item": item.name, "quantity": 1, "dose_unit": item.dose_unit, "staff_disposing_medication": self.worker}]}).insert()
		self.assertFalse(doc.discarded_items[0].get("is_controlled_drug"))
		self.assertEqual(doc.prepared_by, self.worker)
		ensure_r2c1_user_permission(self.worker_b, self.participant_a, applicable_for="Discarded Medication Register")
		with acting_as(self.worker_b):
			crafted = frappe.get_doc("Discarded Medication Register", doc.name)
			crafted.prepared_by = self.worker_b
			with self.assertRaises(frappe.PermissionError):
				crafted.save()
			self.assertNotIn(doc.name, [row.name for row in frappe.get_list("Discarded Medication Register", fields=["name"])])
		doc.reload()
		self.assertEqual(doc.prepared_by, self.worker)
		with acting_as(self.care_manager):
			doc.submit()

	def test_controlled_disposal_requires_distinct_witness_and_creates_transaction(self):
		plan = self.controlled_plan()
		item = plan.medication_items[0]
		self.make_competency(competency_type="Controlled Medication")
		self.make_opening_balance(plan, "2")
		with acting_as(self.care_manager):
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc({"doctype": "Discarded Medication Register", "participant": self.participant_a, "discarded_items": [{"date": today(), "medication_details": "disposed", "medication_plan_item": item.name, "quantity": 1, "dose_unit": item.dose_unit, "is_controlled_drug": 0, "witness": self.worker, "staff_disposing_medication": self.worker}]}).insert()
			doc = frappe.get_doc({"doctype": "Discarded Medication Register", "participant": self.participant_a, "discarded_items": [{"date": today(), "medication_details": "disposed", "medication_plan_item": item.name, "quantity": 1, "dose_unit": item.dose_unit, "is_controlled_drug": 1, "witness": self.system_manager, "staff_disposing_medication": self.worker}]}).insert()
			doc.submit()
		self.assertEqual(frappe.db.count("Controlled Medication Transaction", {"source_docname": doc.name}), 1)
		txn = frappe.db.get_value(
			"Controlled Medication Transaction",
			{"source_docname": doc.name, "docstatus": 1},
			["actor", "finalized_by"],
			as_dict=True,
		)
		self.assertEqual(txn.actor, self.worker)
		self.assertEqual(txn.finalized_by, self.care_manager)
		self.assertTrue(doc.discarded_items[0].is_controlled_drug)
		unqualified = ensure_r2c1_user("R3C2 Unqualified Disposer", ["Support Worker"])
		ensure_r2c1_user_permission(unqualified, self.participant_a, applicable_for="Discarded Medication Register")
		with acting_as(self.care_manager):
			rejected = frappe.get_doc({"doctype": "Discarded Medication Register", "participant": self.participant_a, "discarded_items": [{"date": today(), "medication_details": "disposed", "medication_plan_item": item.name, "quantity": 1, "dose_unit": item.dose_unit, "is_controlled_drug": 1, "witness": self.system_manager, "staff_disposing_medication": unqualified}]}).insert()
			with self.assertRaises(frappe.PermissionError):
				rejected.submit()
		self.assertEqual(frappe.db.count("Controlled Medication Transaction", {"source_docname": rejected.name, "docstatus": 1}), 0)

	def test_disposal_loss_mismatch_or_missing_stock_requires_incident(self):
		plan = self.controlled_plan()
		item = plan.medication_items[0]
		incident = self.make_incident()
		with acting_as(self.care_manager):
			doc = frappe.get_doc({"doctype": "Discarded Medication Register", "participant": self.participant_a, "disposal_status": "Escalated", "discarded_items": [{"date": today(), "medication_details": "missing", "medication_plan_item": item.name, "quantity": 1, "dose_unit": item.dose_unit, "is_controlled_drug": 0, "witness": self.system_manager, "staff_disposing_medication": self.worker}]})
			with self.assertRaises(frappe.ValidationError):
				doc.insert()
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc({"doctype": "Discarded Medication Register", "participant": self.participant_a, "discarded_items": [{"date": today(), "medication_details": "contradictory", "medication_plan_item": item.name, "quantity": 1, "dose_unit": item.dose_unit, "witness": self.system_manager, "staff_disposing_medication": self.worker, "incident_reported": "Yes"}]}).insert()
			escalated = frappe.get_doc({"doctype": "Discarded Medication Register", "participant": self.participant_a, "disposal_status": "Escalated", "discarded_items": [{"date": today(), "medication_details": "missing", "medication_plan_item": item.name, "quantity": 1, "dose_unit": item.dose_unit, "witness": self.system_manager, "staff_disposing_medication": self.worker, "incident_reported": "Yes", "discrepancy_incident": incident.name}]}).insert()
		self.assertEqual(escalated.disposal_status, "Escalated")

	def test_medication_error_and_adverse_reaction_incident_links_are_same_participant(self):
		self.grant_competencies("General Medication")
		plan = self.make_plan()
		incident = self.make_incident("Medication Error", participant=self.participant_b)
		failed_error_count = frappe.db.count("Medication Administration Event", {"incident": incident.name})
		with self.assertRaises(frappe.PermissionError):
			self.make_event(plan, outcome="Error", variance_reason="wrong dose", incident=incident.name).insert()
		self.assertEqual(frappe.db.count("Medication Administration Event", {"incident": incident.name}), failed_error_count)
		adverse_incident = self.make_incident("Adverse Medication Reaction", participant=self.participant_b)
		failed_reaction_count = frappe.db.count("Medication Administration Event", {"incident": adverse_incident.name})
		with self.assertRaises(frappe.PermissionError):
			self.make_event(plan, outcome="Adverse Reaction", variance_reason="rash", incident=adverse_incident.name).insert()
		self.assertEqual(frappe.db.count("Medication Administration Event", {"incident": adverse_incident.name}), failed_reaction_count)
		valid_error = self.make_incident("Medication Error")
		valid_reaction = self.make_incident("Adverse Medication Reaction")
		error_time = f"{add_to_date(today(), days=1)} 08:00:00"
		reaction_time = f"{add_to_date(today(), days=2)} 08:00:00"
		linked_time = f"{add_to_date(today(), days=3)} 08:00:00"
		self.make_event(plan, outcome="Error", variance_reason="wrong dose", incident=valid_error.name, scheduled_datetime=error_time, actual_datetime=error_time).insert()
		self.make_event(plan, outcome="Adverse Reaction", variance_reason="rash", incident=valid_reaction.name, scheduled_datetime=reaction_time, actual_datetime=reaction_time).insert()
		attempted_reported_on = add_to_date(now_datetime(), days=-1)
		with acting_as(self.worker):
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc({"doctype": "Incident", "participant": self.participant_a, "time_of_incident": "08:00:00", "date_of_incident": today(), "location_of_incident": "R3C2 location", "incident_type": "Medication Error", "was_rp_used": "No", "full_description_of_incident": "explicit manager input", "severity": "Low", "reportable_to_commission": "Yes"}).insert()
			spoofed = frappe.get_doc({"doctype": "Incident", "participant": self.participant_a, "reported_by": self.care_manager, "reported_on": attempted_reported_on, "time_of_incident": "08:00:00", "date_of_incident": today(), "location_of_incident": "R3C2 location", "incident_type": "Medication Error", "was_rp_used": "No", "full_description_of_incident": "spoof attempt", "severity": "Low"}).insert()
		self.assertEqual(spoofed.reported_by, self.worker)
		self.assertNotEqual(str(spoofed.reported_on), str(attempted_reported_on))
		self.assertEqual(spoofed.incident_status, "Open")
		self.assertFalse(spoofed.reportable_to_commission)
		self.assertFalse(spoofed.consequence_manager)
		self.assertFalse(spoofed.is_this_likely_to_attract_media_attention)
		self.assertFalse(spoofed.likelihood_manager)
		spoofed.reported_by = self.care_manager
		with self.assertRaises(frappe.ValidationError):
			spoofed.save()
		spoofed.reload()
		with acting_as(self.care_manager):
			spoofed.incident_status = "Closed"
			spoofed.save()
		with acting_as(self.worker):
			self.assertFalse(frappe.has_permission("Incident", "read", doc=spoofed, user=self.worker))
			self.assertFalse(frappe.has_permission("Incident", "write", doc=spoofed, user=self.worker))
			self.assertNotIn(spoofed.name, [row.name for row in frappe.get_list("Incident", fields=["name"])])
		with acting_as(self.care_manager):
			self.assertTrue(frappe.has_permission("Incident", "read", doc=spoofed, user=self.care_manager))
		linked_event = self.submit_event(self.make_event(plan, outcome="Error", variance_reason="wrong dose", incident=valid_error.name, scheduled_datetime=linked_time, actual_datetime=linked_time))
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Incident", valid_error.name).delete()

	def test_query_document_share_and_rollback_guards_cover_new_r3c2_records(self):
		self.assertIn("Controlled Medication Transaction", permissions.PROTECTED_PARTICIPANT_DOCTYPES)
		self.assertIn("Medication PRN Effectiveness Review", permissions.PROTECTED_PARTICIPANT_DOCTYPES)
		self.grant_competencies("General Medication", "Controlled Medication", "PRN Medication")
		plan = self.controlled_plan()
		opening = self.make_opening_balance(plan, "3")
		event = self.submit_event(self.make_event(plan, checker=self.care_manager))
		self.assertFalse(
			permissions.has_participant_document_permission(
				{"doctype": "Controlled Medication Transaction", "participant": self.participant_a}, "read", self.worker
			)
		)
		with acting_as(self.worker):
			self.assertTrue(frappe.has_permission("Medication Administration Event", "read", doc=event, user=self.worker))
			self.assertFalse(frappe.has_permission("Controlled Medication Transaction", "read", user=self.worker))
			with self.assertRaises(frappe.PermissionError):
				frappe.get_list("Controlled Medication Transaction")
			self.assertIn(event.name, [row.name for row in frappe.get_list("Medication Administration Event", fields=["name"])])
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc({"doctype": "Controlled Medication Transaction", "participant": self.participant_a, "medication_plan": plan.name, "medication_plan_item": plan.medication_items[0].name, "transaction_type": "Administration", "quantity": "1", "dose_unit": plan.medication_items[0].dose_unit, "witness": self.system_manager, "source_doctype": "Medication Administration Event", "source_docname": "DIRECT-DENIED", "source_action": "Administration"}).insert()
			self.assertFalse(frappe.has_permission("Controlled Medication Transaction", "write", doc=opening, user=self.worker))
			self.assertFalse(frappe.has_permission("Controlled Medication Transaction", "submit", doc=opening, user=self.worker))
		with acting_as(self.care_manager):
			self.assertTrue(frappe.has_permission("Controlled Medication Transaction", "read", doc=opening, user=self.care_manager))
			self.assertTrue(frappe.has_permission("Controlled Medication Transaction", "write", doc=opening, user=self.care_manager))
		with acting_as(self.coordinator):
			self.assertTrue(frappe.has_permission("Controlled Medication Transaction", "read", doc=opening, user=self.coordinator))
			self.assertFalse(frappe.has_permission("Controlled Medication Transaction", "write", doc=opening, user=self.coordinator))
		share = frappe.get_doc(
			{
				"doctype": "DocShare",
				"share_doctype": "Controlled Medication Transaction",
				"share_name": opening.name,
				"user": self.worker_b,
				"read": 1,
			}
		)
		with self.assertRaises(frappe.PermissionError):
			share.insert(ignore_permissions=True)
		plan_name = plan.name
		medication_item_name = plan.medication_items[0].name
		event_plan_item = event.medication_plan_item
		self.assertFalse(
			permissions.has_participant_access(
				self.participant_a,
				user=self.care_manager,
				applicable_for="Medication Administration Log",
			)
		)
		ensure_r2c1_user_permission(
			self.care_manager,
			self.participant_a,
			applicable_for="Medication Administration Log",
		)
		self.assertTrue(
			permissions.has_participant_access(
				self.participant_a,
				user=self.care_manager,
				applicable_for="Medication Administration Log",
			)
		)
		persisted_plan = frappe.get_doc("Medication Administration Log", plan_name)
		self.assertEqual(persisted_plan.plan_status, "Active")
		self.assertEqual(persisted_plan.medication_items[0].name, medication_item_name)
		self.assertEqual(event_plan_item, medication_item_name)
		archived_plan = frappe.get_doc("Medication Administration Log", plan_name)
		self.assertEqual(archived_plan.plan_status, "Active")
		self.assertEqual(archived_plan.medication_items[0].name, medication_item_name)
		self.assertEqual(frappe.get_doc("Medication Administration Event", event.name).medication_plan_item, medication_item_name)
		archived_plan.lifecycle_reason = "R3C2 rollback guard completed controlled-plan assertions"
		archived_plan.plan_status = "Archived"
		with acting_as(self.care_manager):
			self.assertTrue(
				frappe.has_permission(
					"Medication Administration Log",
					"write",
					doc=archived_plan,
					user=self.care_manager,
				)
			)
			archived_plan.save()
		archived_plan.reload()
		event.reload()
		self.assertEqual(archived_plan.plan_status, "Archived")
		self.assertEqual(archived_plan.lifecycle_reason, "R3C2 rollback guard completed controlled-plan assertions")
		self.assertEqual(archived_plan.medication_items[0].name, medication_item_name)
		self.assertEqual(event.medication_plan, plan_name)
		self.assertEqual(event.medication_plan_item, medication_item_name)
		self.assertTrue(frappe.db.exists("Controlled Medication Transaction", opening.name))
		frappe.db.savepoint("r3c2_rollback_guard")
		transient_review = self.make_submitted_prn_review(self.submit_event(self.make_event(self.prn_plan())))
		self.assertTrue(frappe.db.exists("Medication PRN Effectiveness Review", transient_review.name))
		frappe.db.rollback(save_point="r3c2_rollback_guard")
		self.assertFalse(frappe.db.exists("Medication PRN Effectiveness Review", transient_review.name))
		self.assertTrue(frappe.db.exists("Medication Administration Event", event.name))
		self.assertTrue(frappe.db.exists("Controlled Medication Transaction", opening.name))
		self.assertEqual(frappe.get_doc("Medication Administration Log", plan_name).plan_status, "Archived")
