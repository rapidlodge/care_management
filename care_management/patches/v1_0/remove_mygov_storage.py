"""Remove the empty legacy MyGov storage column after active metadata is removed."""

import frappe
from frappe import _

DOCTYPE = "Participant Profile"
FIELDNAME = "mygov_account"
TABLE = "`tabParticipant Profile`"

HISTORY_COUNT_QUERIES = {
	"version": """
		select count(*)
		from `tabVersion`
		where ref_doctype = 'Participant Profile'
		  and lower(ifnull(data, '')) regexp 'my[_ -]*gov'
	""",
	"error_log": """
		select count(*)
		from `tabError Log`
		where lower(concat_ws(' ', ifnull(method, ''), ifnull(error, ''), ifnull(metadata, '')))
			regexp 'my[_ -]*gov'
	""",
	"activity_log": """
		select count(*)
		from `tabActivity Log`
		where lower(concat_ws(' ', ifnull(subject, ''), ifnull(content, '')))
			regexp 'my[_ -]*gov'
	""",
	"scheduled_job_log": """
		select count(*)
		from `tabScheduled Job Log`
		where lower(concat_ws(' ', ifnull(details, ''), ifnull(debug_log, '')))
			regexp 'my[_ -]*gov'
	""",
	"integration_request": """
		select count(*)
		from `tabIntegration Request`
		where lower(concat_ws(' ', ifnull(request_description, ''), ifnull(data, ''),
			ifnull(output, ''), ifnull(error, ''))) regexp 'my[_ -]*gov'
	""",
	"data_import_log": """
		select count(*)
		from `tabData Import Log` import_log
		inner join `tabData Import` data_import on data_import.name = import_log.data_import
		where data_import.reference_doctype = 'Participant Profile'
		  and lower(concat_ws(' ', ifnull(import_log.messages, ''), ifnull(import_log.exception, '')))
			regexp 'my[_ -]*gov'
	""",
	"access_log_export": """
		select count(*)
		from `tabAccess Log`
		where lower(concat_ws(' ', ifnull(export_from, ''), ifnull(reference_document, ''),
			ifnull(filters, ''), ifnull(columns, ''))) regexp 'my[_ -]*gov'
	""",
}


def _live_counts():
	row = frappe.db.sql(
		f"""
		select
			count(*) as total_rows,
			sum(case when `{FIELDNAME}` is null then 1 else 0 end) as null_rows,
			sum(case when `{FIELDNAME}` = '' then 1 else 0 end) as blank_rows,
			sum(case when `{FIELDNAME}` is not null and `{FIELDNAME}` != '' then 1 else 0 end)
				as nonempty_rows
		from {TABLE}
		""",
		as_dict=True,
	)[0]
	return frappe._dict({key: int(value or 0) for key, value in row.items()})


def _history_reference_counts():
	return {name: int(frappe.db.sql(query)[0][0] or 0) for name, query in HISTORY_COUNT_QUERIES.items()}


def _drop_column():
	frappe.db.sql_ddl(f"alter table {TABLE} drop column `{FIELDNAME}`")


def execute():
	if not frappe.db.has_column(DOCTYPE, FIELDNAME):
		return

	counts = _live_counts()
	if counts.nonempty_rows:
		frappe.throw(
			_("Prohibited-storage remediation requires separate authorization."),
			frappe.ValidationError,
		)

	history_counts = _history_reference_counts()
	if any(history_counts.values()):
		frappe.throw(
			_("Historical prohibited-storage remediation requires separate authorization."),
			frappe.ValidationError,
		)

	_drop_column()
