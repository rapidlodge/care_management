import frappe
from frappe.tests import IntegrationTestCase

from care_management.care_management import permissions
from care_management.care_management.participant_identity import resolve_participant_id
from care_management.care_management.tests.helpers import (
	ensure_r2c1_user,
	ensure_r2c1_user_permission,
	make_r4_participant,
	make_r4_sensitive_identity,
)


class TestParticipantSensitivePermissions(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		run = frappe.generate_hash(length=8)
		self.participant_a = make_r4_participant(f"{run}-A").insert(ignore_permissions=True)
		self.participant_b = make_r4_participant(f"{run}-B").insert(ignore_permissions=True)
		self.details_a = make_r4_sensitive_identity(self.participant_a.name).insert(ignore_permissions=True)
		self.details_b = make_r4_sensitive_identity(self.participant_b.name).insert(ignore_permissions=True)
		self.manager = ensure_r2c1_user(f"R4 Sensitive Manager {run}", ["Care Manager"])
		self.coordinator = ensure_r2c1_user(f"R4 Sensitive Coordinator {run}", ["Support Coordinator"])
		self.worker = ensure_r2c1_user(f"R4 Sensitive Worker {run}", ["Support Worker"])
		for user in (self.manager, self.coordinator, self.worker):
			ensure_r2c1_user_permission(
				user,
				self.participant_a.name,
				applicable_for="Participant Sensitive Identity",
			)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def test_01_guest_is_denied(self):
		self.assertFalse(
			permissions.has_participant_document_permission(self.details_a, "read", user="Guest")
		)

	def test_02_support_worker_is_denied(self):
		self.assertFalse(
			permissions.has_participant_document_permission(self.details_a, "read", user=self.worker)
		)

	def test_03_granted_manager_can_create(self):
		doc = make_r4_sensitive_identity(self.participant_a.name)
		self.assertTrue(frappe.has_permission(doc.doctype, "create", doc=doc, user=self.manager))

	def test_04_ungranted_manager_cannot_create(self):
		doc = make_r4_sensitive_identity(self.participant_b.name)
		self.assertFalse(frappe.has_permission(doc.doctype, "create", doc=doc, user=self.manager))

	def test_05_granted_manager_can_read_and_write(self):
		for permission_type in ("read", "write"):
			self.assertTrue(
				frappe.has_permission(
					self.details_a.doctype,
					permission_type,
					doc=self.details_a,
					user=self.manager,
				)
			)

	def test_06_cross_participant_document_access_is_denied(self):
		self.assertFalse(
			frappe.has_permission(
				self.details_b.doctype,
				"read",
				doc=self.details_b,
				user=self.manager,
			)
		)

	def test_07_list_query_returns_only_granted_participant(self):
		frappe.set_user(self.manager)
		names = set(frappe.get_list("Participant Sensitive Identity", pluck="name"))
		self.assertIn(self.details_a.name, names)
		self.assertNotIn(self.details_b.name, names)

	def test_08_coordinator_can_read_granted_record(self):
		self.assertTrue(
			frappe.has_permission(
				self.details_a.doctype,
				"read",
				doc=self.details_a,
				user=self.coordinator,
			)
		)

	def test_09_coordinator_cannot_write(self):
		self.assertFalse(
			frappe.has_permission(
				self.details_a.doctype,
				"write",
				doc=self.details_a,
				user=self.coordinator,
			)
		)

	def test_10_identifier_knowledge_does_not_grant_protected_access(self):
		participant_id = self.participant_b.participant_id
		self.assertIsNone(resolve_participant_id(participant_id, user=self.manager))
		self.assertFalse(
			frappe.has_permission(
				self.details_b.doctype,
				"read",
				doc=self.details_b,
				user=self.manager,
			)
		)

	def test_11_standard_api_denies_cross_participant_read(self):
		from frappe.client import get

		frappe.set_user(self.manager)
		self.assertRaises(frappe.PermissionError, get, self.details_b.doctype, self.details_b.name)

	def test_12_standard_api_allows_granted_read(self):
		from frappe.client import get

		frappe.set_user(self.manager)
		result = get(self.details_a.doctype, self.details_a.name)
		self.assertEqual(result.name, self.details_a.name)

	def test_13_query_condition_fails_closed_without_grant(self):
		ungranted = ensure_r2c1_user(
			f"R4 Sensitive Ungranted {frappe.generate_hash(length=8)}", ["Care Manager"]
		)
		self.assertEqual(
			permissions.get_participant_permission_query_conditions(
				"Participant Sensitive Identity", user=ungranted
			),
			"1=0",
		)

	def test_14_import_and_export_are_not_broadly_available(self):
		meta = frappe.get_meta("Participant Sensitive Identity")
		self.assertFalse(meta.allow_import)
		care_manager_permission = next(row for row in meta.permissions if row.role == "Care Manager")
		self.assertFalse(care_manager_permission.get("export"))
