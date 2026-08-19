from frappe import _

def get_data():
    return {
        "fieldname": "source_docname",
        "non_standard_fieldnames": {
            "Support Task": "source_docname",
        },
        "transactions": [
            {
                "label": _("Operations & Execution"),
                "items": ["Support Task"]
            }
        ]
    }