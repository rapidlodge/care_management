import json
from pathlib import Path

import frappe
from frappe.core.doctype.data_export.exporter import DataExporter
from frappe.core.doctype.data_import.importer import Column
from frappe.desk import reportview
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from care_management.care_management.prohibited_storage import (
	PROHIBITED_MYGOV_FIELDNAMES,
	is_prohibited_mygov_identifier,
)
from care_management.care_management.tests.helpers import ensure_r2c1_user, make_r4_participant


def _background_insert(payload):
	frappe.get_doc(payload).insert(ignore_permissions=True)


class TestMyGovProhibitedStorage(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def _new_payload(self, suffix=None):
		doc = make_r4_participant(suffix or frappe.generate_hash(length=8))
		return doc.as_dict()

	def _insert_participant(self):
		return make_r4_participant(frappe.generate_hash(length=8)).insert(ignore_permissions=True)

	def _assert_insert_denied_for_user(self, user):
		payload = self._new_payload()
		payload["mygov_account"] = "must-not-store"
		frappe.set_user(user)
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			frappe.client.insert(payload)

	def test_01_active_metadata_is_absent(self):
		meta = frappe.get_meta("Participant Profile")
		self.assertFalse(meta.has_field("mygov_account"))
		self.assertFalse(any(is_prohibited_mygov_identifier(row.fieldname) for row in meta.fields))

	def test_02_standard_document_serialization_is_absent(self):
		doc = self._insert_participant()
		self.assertFalse(PROHIBITED_MYGOV_FIELDNAMES.intersection(doc.as_dict()))

	def test_03_document_insert_rejects_prohibited_field(self):
		doc = make_r4_participant(frappe.generate_hash(length=8))
		doc.__dict__["mygov_account"] = "must-not-store"
		with self.assertRaisesRegex(frappe.ValidationError, "Prohibited credential storage"):
			doc.insert(ignore_permissions=True)

	def test_04_existing_document_save_rejects_prohibited_field(self):
		doc = self._insert_participant()
		doc.__dict__["mygov_account"] = "must-not-store"
		with self.assertRaisesRegex(frappe.ValidationError, "Prohibited credential storage"):
			doc.save(ignore_permissions=True)

	def test_05_alias_variants_are_rejected(self):
		for alias in (
			"mygov",
			"my_gov",
			"my-gov-id",
			"MyGov Account",
			"mygov_username",
			"mygov_password",
			"mygov_portal_access",
		):
			with self.subTest(alias=alias):
				doc = make_r4_participant(frappe.generate_hash(length=8))
				doc.__dict__[alias] = "must-not-store"
				with self.assertRaises(frappe.ValidationError):
					doc.insert(ignore_permissions=True)

	def test_06_desk_equivalent_insert_is_denied(self):
		payload = self._new_payload()
		payload["mygov_account"] = "must-not-store"
		with self.assertRaisesRegex(frappe.ValidationError, "Prohibited credential storage"):
			frappe.client.insert(payload)

	def test_07_standard_rest_insert_is_denied(self):
		payload = self._new_payload()
		payload["mygov_login"] = "must-not-store"
		with self.assertRaises(frappe.ValidationError):
			frappe.client.insert(json.dumps(payload, default=str))

	def test_08_standard_rest_update_is_denied(self):
		doc = self._insert_participant()
		payload = doc.as_dict()
		payload["mygov_account"] = "must-not-store"
		with self.assertRaisesRegex(frappe.ValidationError, "Prohibited credential storage"):
			frappe.client.save(payload)

	def test_09_data_import_cannot_map_prohibited_field(self):
		column = Column(0, "MyGov Account", "Participant Profile", ["must-not-store"])
		self.assertTrue(column.skip_import)
		self.assertIsNone(column.df)

	def test_10_background_document_write_is_denied(self):
		payload = self._new_payload()
		payload["mygov_account"] = "must-not-store"
		with self.assertRaises(frappe.ValidationError):
			frappe.enqueue(_background_insert, now=True, payload=payload)

	def test_11_copy_cannot_reproduce_prohibited_storage(self):
		doc = self._insert_participant()
		copy = frappe.copy_doc(doc)
		self.assertNotIn("mygov_account", copy.as_dict())
		copy.__dict__["mygov_account"] = "must-not-store"
		with self.assertRaises(frappe.ValidationError):
			copy.insert(ignore_permissions=True)

	def test_12_get_value_cannot_select_prohibited_field(self):
		doc = self._insert_participant()
		with self.assertRaises(frappe.ValidationError):
			frappe.client.get_value(
				"Participant Profile",
				"mygov_account",
				filters={"name": doc.name},
			)

	def test_13_get_list_cannot_select_prohibited_field(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.client.get_list("Participant Profile", fields=["name", "mygov_account"])

	def test_14_reportview_cannot_select_prohibited_field(self):
		frappe.local.request = frappe._dict(method="POST")
		frappe.local.form_dict = frappe._dict(
			{
				"doctype": "Participant Profile",
				"fields": ["name", "mygov_account"],
				"view": "Report",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			reportview.get()

	def test_15_export_cannot_select_prohibited_field(self):
		exporter = DataExporter(
			doctype="Participant Profile",
			with_data=True,
			select_columns={"Participant Profile": ["name", "mygov_account"]},
			file_type="CSV",
		)
		exporter.build_response()
		self.assertNotIn("mygov", str(frappe.response.get("result", "")).lower())

	def test_16_standard_print_contains_no_prohibited_field(self):
		doc = self._insert_participant()
		frappe.local.request = Request(EnvironBuilder(method="GET", path="/printview").get_environ())
		html = frappe.get_print("Participant Profile", doc.name)
		self.assertNotIn("mygov", html.lower())

	def test_17_guest_cannot_store_prohibited_field(self):
		self._assert_insert_denied_for_user("Guest")

	def test_18_care_manager_cannot_store_prohibited_field(self):
		user = ensure_r2c1_user(f"R4 MyGov Manager {frappe.generate_hash(length=8)}", ["Care Manager"])
		self._assert_insert_denied_for_user(user)

	def test_19_system_manager_cannot_store_prohibited_field(self):
		user = ensure_r2c1_user(
			f"R4 MyGov System Manager {frappe.generate_hash(length=8)}", ["System Manager"]
		)
		self._assert_insert_denied_for_user(user)

	def test_20_administrator_cannot_store_prohibited_field(self):
		self._assert_insert_denied_for_user("Administrator")

	def test_21_custom_field_reintroduction_is_denied(self):
		doc = frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Participant Profile",
				"fieldname": "mygov_portal",
				"label": "Portal",
				"fieldtype": "Data",
			}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "Prohibited credential storage metadata"):
			doc.insert(ignore_permissions=True)

	def test_22_property_setter_reintroduction_is_denied(self):
		doc = frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doctype_or_field": "DocField",
				"doc_type": "Participant Profile",
				"field_name": "participant",
				"property": "label",
				"value": "MyGov Portal",
				"property_type": "Data",
			}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "Prohibited credential storage metadata"):
			doc.insert(ignore_permissions=True)

	def test_23_cross_app_metadata_and_fixtures_do_not_reintroduce_storage(self):
		apps = ("care_management", "ndis_crm", "ndis_finance", "crm", "frappe", "erpnext")
		findings = []
		for app in apps:
			root = Path(frappe.get_app_path(app)).parent
			for path in root.rglob("*.json"):
				if any(part in {"node_modules", ".git", "dist", "build"} for part in path.parts):
					continue
				try:
					data = json.loads(path.read_text(encoding="utf-8"))
				except (OSError, json.JSONDecodeError, UnicodeDecodeError):
					continue
				for field in data.get("fields", []) if isinstance(data, dict) else ():
					if is_prohibited_mygov_identifier(field.get("fieldname")):
						findings.append((app, path.name, field.get("fieldname")))
		self.assertEqual(findings, [])
