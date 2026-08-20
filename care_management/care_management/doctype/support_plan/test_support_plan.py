# Copyright (c) 2026, Hex Flow and Contributors
# See license.txt

from frappe.tests import IntegrationTestCase

from care_management.care_management.tests.helpers import assert_care_doctype_metadata

IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Appointment Schedule",
	"Daily Food Diary",
	"Epilepsy Management Plan",
	"Falls Risk Plan",
	"Hospital Support Plan",
	"Medical Report Summary",
	"Medication Administration Log",
	"Participant Profile",
	"Skin Integrity Form",
	"User",
	"Weekly Meal Planner",
]

class TestSupportPlan(IntegrationTestCase):
	def test_doctype_metadata(self):
		assert_care_doctype_metadata(self, "Support Plan")
