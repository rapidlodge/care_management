# Copyright (c) 2026, Hex Flow and Contributors
# See license.txt

from frappe.tests import IntegrationTestCase

from care_management.care_management.tests.helpers import assert_care_doctype_metadata

IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Incident",
	"Participant Profile",
	"User",
]

class TestIncident(IntegrationTestCase):
	def test_doctype_metadata(self):
		assert_care_doctype_metadata(self, "Incident")
