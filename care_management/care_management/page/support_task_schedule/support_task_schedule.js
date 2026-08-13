frappe.pages['support-task-schedule'].on_page_load = function(wrapper) {
    let page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Active Support Tasks Scheduler',
        single_column: true
    });

    wrapper.scheduler = new SupportTaskScheduler(page);
};


class SupportTaskScheduler {

    constructor(page) {

        this.page = page;

        this.current_start_date =
            moment().startOf('isoWeek');

        this.selected_task_id = null;
        this.selected_occurrence_date = null;

        this.filter_participant = null;
        this.filter_participant_label = null;
        this.filter_category = null;
        this.filter_shift = this.get_current_shift();

        this.tracker_config = {

            'Mood Tracker':
                'Mood Tracker Entry',

            'Sleep Tracker':
                'Sleep Tracker Entry',

            'Shower Chart':
                'Shower Chart Item',

            'Daily Bowel Record Chart':
                'Daily Bowel Record Item',

            'Fluid Intake Output Chart':
                'Fluid Intake Item',

            'Weekly Exercise Record':
                'Exercise Record Item',

            'Seizure Chart':
                'Seizure Chart Entry'
        };


        this.make_layout();

        this.load_schedule_grid();
    }


    // ================================================================
    // CURRENT SHIFT
    // ================================================================

    get_current_shift() {

        let mins =
            moment().hours() * 60 +
            moment().minutes();


        if (
            mins >= 6 * 60 &&
            mins < 14 * 60
        ) {
            return 'AM Shift';
        }


        if (
            mins >= 14 * 60 &&
            mins < 22 * 60
        ) {
            return 'PM Shift';
        }


        return 'Night Shift';
    }


    // ================================================================
    // PAGE LAYOUT
    // ================================================================

    make_layout() {

        let me = this;


        // ------------------------------------------------------------
        // WEEK NAVIGATION
        // ------------------------------------------------------------

        this.page.set_secondary_action(
            'Previous Week',
            function() {

                me.current_start_date.subtract(
                    7,
                    'days'
                );

                me.load_schedule_grid();
            }
        );


        this.page.set_primary_action(
            'Next Week',
            function() {

                me.current_start_date.add(
                    7,
                    'days'
                );

                me.load_schedule_grid();
            }
        );


        // ------------------------------------------------------------
        // HTML
        // ------------------------------------------------------------

        let html = `

        <style>

            .task-card-box {

                transition:
                    transform 0.15s ease,
                    box-shadow 0.15s ease;

                touch-action:
                    manipulation;

                -webkit-tap-highlight-color:
                    transparent;
            }


            .task-card-box:active {

                transform:
                    scale(0.97);
            }


            #support-task-filter-bar
            .form-group {

                margin-bottom:
                    0;
            }


            #support-task-filter-bar
            .control-label {

                font-weight:
                    600;

                margin-bottom:
                    5px;
            }


            @media (max-width: 768px) {

                .matrix-table-container {

                    overflow-x:
                        scroll;
                }


                .inspector-flex {

                    flex-direction:
                        column !important;
                }


                .btn-action-touch {

                    min-height:
                        44px;

                    width:
                        100%;

                    margin-bottom:
                        6px;
                }


                #support-task-filter-bar {

                    flex-direction:
                        column;

                    align-items:
                        stretch !important;
                }


                #participant-filter-container,
                #category-filter-container,
                #shift-filter-container {

                    min-width:
                        100% !important;

                    width:
                        100%;
                }

            }

        </style>


        <div style="padding: 8px;">


            <!-- =====================================================
                 HEADER
                 ===================================================== -->

            <div
                style="
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    background: #eef2f5;
                    padding: 10px 14px;
                    border-radius: 6px;
                    margin-bottom: 12px;
                    border: 1px solid #d1d8dd;
                "
            >

                <div
                    id="week-date-range-heading"
                    style="
                        font-weight: bold;
                        color: #1c2b36;
                        font-size: 14px;
                    "
                >
                    Week View
                </div>


                <div>

                    <span
                        class="badge badge-info"
                        style="
                            font-size: 11px;
                            padding: 5px 10px;
                        "
                    >
                        Frontline Shift Board
                    </span>

                </div>

            </div>


            <!-- =====================================================
                 FILTER BAR
                 ===================================================== -->

            <div
                id="support-task-filter-bar"
                style="
                    display: flex;
                    gap: 12px;
                    align-items: flex-end;
                    flex-wrap: wrap;
                    padding: 12px;
                    margin-bottom: 12px;
                    background: #f8f9fa;
                    border: 1px solid #d1d8dd;
                    border-radius: 6px;
                "
            >

                <div
                    id="participant-filter-container"
                    style="
                        min-width: 240px;
                        flex: 1;
                    "
                ></div>


                <div
                    id="category-filter-container"
                    style="
                        min-width: 220px;
                    "
                ></div>


                <div
                    id="shift-filter-container"
                    style="
                        min-width: 180px;
                    "
                ></div>

            </div>


            <!-- =====================================================
                 WEEKLY MATRIX
                 ===================================================== -->

            <div
                class="matrix-table-container"
                style="
                    border: 1px solid #d1d8dd;
                    border-radius: 6px;
                    background: #fff;
                "
            >

                <table
                    style="
                        width: 100%;
                        min-width: 850px;
                        border-collapse: collapse;
                        text-align: left;
                        font-size: 12px;
                    "
                >

                    <thead>

                        <tr
                            style="
                                background-color: #f7f9fa;
                                border-bottom: 2px solid #d1d8dd;
                                text-align: center;
                            "
                        >

                            <th
                                style="
                                    padding: 10px;
                                    border-right: 1px solid #d1d8dd;
                                    width: 90px;
                                "
                            >
                                Time
                            </th>


                            <th
                                id="th-day-0"
                                style="
                                    padding: 10px;
                                    border-right: 1px solid #d1d8dd;
                                "
                            >
                                Mon
                            </th>


                            <th
                                id="th-day-1"
                                style="
                                    padding: 10px;
                                    border-right: 1px solid #d1d8dd;
                                "
                            >
                                Tue
                            </th>


                            <th
                                id="th-day-2"
                                style="
                                    padding: 10px;
                                    border-right: 1px solid #d1d8dd;
                                "
                            >
                                Wed
                            </th>


                            <th
                                id="th-day-3"
                                style="
                                    padding: 10px;
                                    border-right: 1px solid #d1d8dd;
                                "
                            >
                                Thu
                            </th>


                            <th
                                id="th-day-4"
                                style="
                                    padding: 10px;
                                    border-right: 1px solid #d1d8dd;
                                "
                            >
                                Fri
                            </th>


                            <th
                                id="th-day-5"
                                style="
                                    padding: 10px;
                                    border-right: 1px solid #d1d8dd;
                                "
                            >
                                Sat
                            </th>


                            <th
                                id="th-day-6"
                                style="
                                    padding: 10px;
                                    border-right: 1px solid #d1d8dd;
                                "
                            >
                                Sun
                            </th>


                            <th
                                style="
                                    padding: 10px;
                                    background-color: #fff9db;
                                "
                            >
                                Floating Tasks
                            </th>

                        </tr>

                    </thead>


                    <tbody id="matrix-body"></tbody>

                </table>

            </div>


            <!-- =====================================================
                 TASK INSPECTOR
                 ===================================================== -->

            <div
                style="
                    margin-top: 16px;
                    border: 1px solid #b8c2cc;
                    border-radius: 6px;
                    background: #fff;
                    box-shadow:
                        0 4px 12px rgba(0,0,0,0.06);
                "
            >

                <div
                    style="
                        background: #e9ecef;
                        padding: 10px 14px;
                        border-bottom: 1px solid #d1d8dd;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        flex-wrap: wrap;
                        gap: 8px;
                    "
                >

                    <div
                        id="inspector-title"
                        style="
                            font-weight: bold;
                            color: #2b2b2b;
                        "
                    >
                        Task Inspector Panel
                    </div>


                    <div
                        style="
                            display: flex;
                            gap: 8px;
                            flex-wrap: wrap;
                        "
                    >

                        <button class="btn btn-sm btn-primary btn-action-touch"
                                id="btn-start-task">
                            <i class="fa fa-play"></i> Start Task
                        </button>

                        <button class="btn btn-sm btn-success btn-action-touch"
                                id="btn-record-outcome">
                            <i class="fa fa-check"></i> Record Outcome
                        </button>

                        <button class="btn btn-sm btn-warning btn-action-touch"
                                id="btn-log-missed">
                            <i class="fa fa-exclamation-triangle"></i> Log Missed
                        </button>

                        <button class="btn btn-sm btn-secondary btn-action-touch"
                                id="btn-fill-tracker">
                            <i class="fa fa-list"></i> Fill Tracker
                        </button>

                    </div>

                </div>


                <div
                    id="inspector-content"
                    class="inspector-flex"
                    style="
                        display: flex;
                        padding: 14px;
                        gap: 16px;
                    "
                >

                    <div
                        id="panel-left-details"
                        style="
                            flex: 1;
                            background: #e7f5ff;
                            border: 1px solid #a5d8ff;
                            padding: 12px;
                            border-radius: 6px;
                        "
                    >

                        <p style="margin: 4px 0;">

                            <em>
                                Tap any task card above to inspect
                                instructions and record outcome.
                            </em>

                        </p>

                    </div>

                </div>

            </div>

            <!-- =====================================================
                 PHASE 3B - MANAGER REVIEW
                 ===================================================== -->

            <div
                id="manager-review-section"
                style="
                    margin-top: 16px;
                    border: 1px solid #b8c2cc;
                    border-radius: 6px;
                    background: #fff;
                    box-shadow:
                        0 4px 12px rgba(0,0,0,0.06);
                "
            >

                <div
                    style="
                        background: #e9ecef;
                        padding: 10px 14px;
                        border-bottom: 1px solid #d1d8dd;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        flex-wrap: wrap;
                        gap: 8px;
                    "
                >

                    <div>

                        <div
                            style="
                                font-weight: bold;
                                color: #2b2b2b;
                            "
                        >
                            Manager Review
                        </div>

                        <div
                            style="
                                font-size: 11px;
                                color: #6c757d;
                                margin-top: 2px;
                            "
                        >
                            Review execution outcomes,
                            exceptions, missed tasks and
                            follow-up requirements.
                        </div>

                    </div>

                    <button
                        class="
                            btn
                            btn-sm
                            btn-secondary
                            btn-action-touch
                        "
                        id="btn-refresh-manager-review"
                    >
                        <i class="fa fa-refresh"></i>
                        Refresh
                    </button>

                </div>

                <div
                    style="
                        padding: 12px;
                        border-bottom: 1px solid #e9ecef;
                        background: #f8f9fa;
                    "
                >

                    <div
                        style="
                            display: flex;
                            gap: 10px;
                            align-items: flex-end;
                            flex-wrap: wrap;
                        "
                    >

                        <div
                            style="
                                min-width: 180px;
                            "
                        >

                            <label
                                style="
                                    display: block;
                                    font-weight: 600;
                                    font-size: 11px;
                                    margin-bottom: 4px;
                                "
                            >
                                Start Date
                            </label>

                            <input
                                type="date"
                                class="form-control input-sm"
                                id="manager-review-start-date"
                            >

                        </div>

                        <div
                            style="
                                min-width: 180px;
                            "
                        >

                            <label
                                style="
                                    display: block;
                                    font-weight: 600;
                                    font-size: 11px;
                                    margin-bottom: 4px;
                                "
                            >
                                End Date
                            </label>

                            <input
                                type="date"
                                class="form-control input-sm"
                                id="manager-review-end-date"
                            >

                        </div>

                        <div
                            style="
                                min-width: 200px;
                            "
                        >

                            <label
                                style="
                                    display: block;
                                    font-weight: 600;
                                    font-size: 11px;
                                    margin-bottom: 4px;
                                "
                            >
                                Status
                            </label>

                            <select
                                class="form-control input-sm"
                                id="manager-review-status"
                            >

                                <option value="">
                                    All
                                </option>

                                <option value="Delivered">
                                    Delivered
                                </option>

                                <option value="Partially Completed">
                                    Partially Completed
                                </option>

                                <option value="Refused / Declined">
                                    Refused / Declined
                                </option>

                                <option value="Not Applicable">
                                    Not Applicable
                                </option>

                                <option value="Missed">
                                    Missed
                                </option>

                                <option value="Cancelled">
                                    Cancelled
                                </option>

                                <option value="In Progress">
                                    In Progress
                                </option>

                            </select>

                        </div>

                        <button
                            class="
                                btn
                                btn-sm
                                btn-primary
                                btn-action-touch
                            "
                            id="btn-apply-manager-review"
                        >
                            <i class="fa fa-filter"></i>
                            Apply
                        </button>

                    </div>

                </div>

                <div
                    id="manager-review-summary"
                    style="
                        padding: 12px;
                        border-bottom: 1px solid #e9ecef;
                    "
                ></div>

                <div
                    id="manager-review-results"
                    style="
                        padding: 12px;
                    "
                ></div>

            </div>

        </div>
        `;


        $(this.page.body).html(html);




        // ============================================================
        // PARTICIPANT FILTER
        // ============================================================

        let participant_filter =
            frappe.ui.form.make_control({

                parent:
                    $('#participant-filter-container'),

                df: {

                    fieldname:
                        'participant_filter',

                    label:
                        'Participant',

                    fieldtype:
                        'Link',

                    options:
                        'Participant Profile',

                    change:
                        function() {

                            me.filter_participant =
                                this.get_value() || null;

                            /*
                             * Link controls have a display value
                             * which may be different from the
                             * document name.
                             */
                            me.filter_participant_label =
                                this.get_input_value
                                    ? this.get_input_value()
                                    : null;

                            me.load_schedule_grid();
                        }

                },

                render_input:
                    true

            });


        participant_filter.set_value(
            this.filter_participant || ''
        );


        // ============================================================
        // CATEGORY FILTER
        // ============================================================

        frappe.model.with_doctype(
            'Support Task',
            function() {

                let task_meta =
                    frappe.get_meta(
                        'Support Task'
                    );


                let category_df =
                    task_meta &&
                    task_meta.fields
                        ? task_meta.fields.find(
                            function(df) {

                                return (
                                    df.fieldname ===
                                    'task_category'
                                );

                            }
                        )
                        : null;


                let category_options = [];


                if (
                    category_df &&
                    category_df.options
                ) {

                    category_options =
                        String(
                            category_df.options
                        )
                            .split('\n')
                            .map(
                                function(value) {

                                    return value.trim();

                                }
                            )
                            .filter(
                                function(value) {

                                    return value !== '';

                                }
                            );

                }


                let category_filter =
                    frappe.ui.form.make_control({

                        parent:
                            $('#category-filter-container'),

                        df: {

                            fieldname:
                                'category_filter',

                            label:
                                'Category',

                            fieldtype:
                                'Select',

                            options:
                                ['']
                                    .concat(
                                        category_options
                                    )
                                    .join('\n'),

                            change:
                                function() {

                                    me.filter_category =
                                        this.get_value() ||
                                        null;

                                    me.load_schedule_grid();

                                }

                        },

                        render_input:
                            true

                    });


                category_filter.set_value(
                    me.filter_category || ''
                );

            }
        );


        // ============================================================
        // SHIFT FILTER
        // ============================================================

        let shift_filter =
            frappe.ui.form.make_control({

                parent:
                    $('#shift-filter-container'),

                df: {

                    fieldname:
                        'shift_filter',

                    label:
                        'Shift',

                    fieldtype:
                        'Select',

                    options:
                        'AM Shift\nPM Shift\nNight Shift',

                    default:
                        this.filter_shift,

                    change:
                        function() {

                            me.filter_shift =
                                this.get_value() ||
                                null;

                            me.load_schedule_grid();

                        }

                },

                render_input:
                    true

            });


        shift_filter.set_value(
            this.filter_shift ||
            this.get_current_shift()
        );


        this.filter_shift =
            shift_filter.get_value() ||
            this.get_current_shift();


        // ============================================================
        // BUTTON EVENTS
        // ============================================================

        $('#btn-start-task').on('click', function() {
            me.start_task_execution();
        });

        $('#btn-record-outcome').on('click', function() {
            me.show_outcome_dialog();
        });

        $('#btn-log-missed').on('click', function() {
            me.show_missed_dialog();
        });

        $('#btn-fill-tracker').on('click', function() {
            me.show_tracker_picker();
        });


        $('#btn-fill-tracker').on(
            'click',
            function() {

                me.show_tracker_picker();

            }
        );

        // ============================================================
        // PHASE 3B - MANAGER REVIEW
        // ============================================================

        this.initialize_manager_review();
    }


    // ================================================================
    // TRACKER PICKER
    // ================================================================

    show_tracker_picker() {

        let me = this;


        let picker =
            new frappe.ui.Dialog({

                title:
                    'Fill Tracker Chart',

                fields: [

                    {
                        label:
                            'Participant',

                        fieldname:
                            'participant',

                        fieldtype:
                            'Link',

                        options:
                            'Participant Profile',

                        reqd:
                            1,

                        default:
                            me.filter_participant ||
                            ''
                    },


                    {
                        label:
                            'Tracker / Chart',

                        fieldname:
                            'tracker_doctype',

                        fieldtype:
                            'Select',

                        options:
                            Object.keys(
                                me.tracker_config
                            ).join('\n'),

                        reqd:
                            1
                    }

                ],


                primary_action_label:
                    'Open Grid',


                primary_action:
                    function(values) {

                        if (
                            !values.participant
                        ) {

                            frappe.msgprint(
                                'Please select a Participant.'
                            );

                            return;
                        }


                        if (
                            !values.tracker_doctype
                        ) {

                            frappe.msgprint(
                                'Please select a Tracker / Chart.'
                            );

                            return;
                        }


                        picker.hide();


                        setTimeout(
                            function() {

                                me.show_tracker_matrix_dialog(

                                    values.participant,

                                    values.tracker_doctype

                                );

                            },
                            200
                        );

                    }

            });


        picker.show();
    }


    // ================================================================
    // TRACKER GRID
    // ================================================================

    show_tracker_matrix_dialog(
        participant,
        tracker_doctype
    ) {

        let me = this;


        let item_doctype =
            this.tracker_config[
                tracker_doctype
            ];


        if (!item_doctype) {

            frappe.msgprint(
                `No tracker configuration found for ${tracker_doctype}.`
            );

            return;
        }


        /*
         * Load the Child Table metadata before creating
         * the Dialog Table field.
         */
        frappe.model.with_doctype(
            item_doctype,
            function() {

                let meta =
                    frappe.get_meta(
                        item_doctype
                    );


                if (
                    !meta ||
                    !meta.fields
                ) {

                    frappe.msgprint(
                        `Unable to load DocType metadata for ${item_doctype}.`
                    );

                    return;
                }


                let usable_fields =
                    meta.fields.filter(
                        function(df) {

                            return ![
                                'Section Break',
                                'Column Break',
                                'Tab Break',
                                'HTML',
                                'Button'
                            ].includes(
                                df.fieldtype
                            );

                        }
                    );


                let grid_fields =
                    usable_fields
                        .filter(
                            function(df) {

                                return (
                                    df.in_list_view ||
                                    df.reqd
                                );

                            }
                        )
                        .map(
                            function(df) {

                                let field = {

                                    fieldname:
                                        df.fieldname,

                                    label:
                                        df.label ||
                                        df.fieldname,

                                    fieldtype:
                                        df.fieldtype,

                                    in_list_view:
                                        1,

                                    reqd:
                                        df.reqd
                                            ? 1
                                            : 0
                                };


                                if (
                                    df.options
                                ) {

                                    field.options =
                                        df.options;

                                }


                                if (
                                    df.default !==
                                    undefined
                                ) {

                                    field.default =
                                        df.default;

                                }


                                if (
                                    df.read_only
                                ) {

                                    field.read_only =
                                        1;

                                }


                                if (
                                    df.description
                                ) {

                                    field.description =
                                        df.description;

                                }


                                if (
                                    df.precision
                                ) {

                                    field.precision =
                                        df.precision;

                                }


                                return field;

                            }
                        );


                /*
                 * Fallback if nothing is marked in_list_view.
                 */
                if (
                    !grid_fields.length
                ) {

                    grid_fields =
                        usable_fields.map(
                            function(df) {

                                let field = {

                                    fieldname:
                                        df.fieldname,

                                    label:
                                        df.label ||
                                        df.fieldname,

                                    fieldtype:
                                        df.fieldtype,

                                    in_list_view:
                                        1,

                                    reqd:
                                        df.reqd
                                            ? 1
                                            : 0

                                };


                                if (
                                    df.options
                                ) {

                                    field.options =
                                        df.options;

                                }


                                if (
                                    df.default !==
                                    undefined
                                ) {

                                    field.default =
                                        df.default;

                                }


                                return field;

                            }
                        );

                }


                if (
                    !grid_fields.length
                ) {

                    frappe.msgprint(
                        `No usable fields were found in ${item_doctype}.`
                    );

                    return;
                }


                console.log(
                    '[Tracker Grid]',
                    tracker_doctype,
                    item_doctype,
                    grid_fields
                );


                let d =
                    new frappe.ui.Dialog({

                        title:
                            `${tracker_doctype} - Matrix Entry (${participant})`,

                        size:
                            'extra-large',


                        fields: [

                            {
                                label:
                                    'Entries',

                                fieldname:
                                    'entries',

                                fieldtype:
                                    'Table',

                                fields:
                                    grid_fields,

                                in_place_edit:
                                    true,

                                cannot_add_rows:
                                    false,

                                cannot_delete_rows:
                                    false
                            }

                        ],


                        primary_action_label:
                            'Save Entries',


                        primary_action:
                            function(values) {

                                let rows =
                                    values.entries ||
                                    [];


                                if (
                                    !rows.length
                                ) {

                                    frappe.msgprint(
                                        'Add at least one row to the grid before saving.'
                                    );

                                    return;
                                }


                                rows =
                                    rows.map(
                                        function(row) {

                                            let clean =
                                                Object.assign(
                                                    {},
                                                    row
                                                );


                                            delete clean.name;
                                            delete clean.idx;
                                            delete clean.parent;
                                            delete clean.parentfield;
                                            delete clean.parenttype;
                                            delete clean.doctype;
                                            delete clean.owner;
                                            delete clean.creation;
                                            delete clean.modified;
                                            delete clean.modified_by;
                                            delete clean.docstatus;


                                            return clean;

                                        }
                                    );


                                frappe.call({

                                    method:
                                        'care_management.care_management.page.support_task_schedule.support_task_schedule.save_tracker_matrix_entries',


                                    args: {

                                        participant:
                                            participant,

                                        tracker_doctype:
                                            tracker_doctype,

                                        rows:
                                            rows

                                    },


                                    freeze:
                                        true,


                                    freeze_message:
                                        'Saving tracker entries...',


                                    callback:
                                        function(r) {

                                            if (
                                                r.message &&
                                                r.message.status ===
                                                    'success'
                                            ) {

                                                frappe.show_alert({

                                                    message:
                                                        `${r.message.rows_saved} entr${r.message.rows_saved === 1 ? 'y' : 'ies'} saved to ${tracker_doctype}.`,

                                                    indicator:
                                                        'green'

                                                });


                                                d.hide();

                                            }

                                            else {

                                                frappe.msgprint({

                                                    title:
                                                        'Save Failed',

                                                    message:
                                                        (
                                                            r.message &&
                                                            r.message.message
                                                        )
                                                            ?
                                                            r.message.message
                                                            :
                                                            'Unable to save tracker entries.',

                                                    indicator:
                                                        'red'

                                                });

                                            }

                                        },


                                    error:
                                        function() {

                                            frappe.msgprint({

                                                title:
                                                    'Error',

                                                message:
                                                    'An error occurred while saving tracker entries.',

                                                indicator:
                                                    'red'

                                            });

                                        }

                                });

                            }

                    });


                d.show();

            }
        );
    }


    // ================================================================
    // LOAD SCHEDULE
    // ================================================================

    load_schedule_grid() {

        let me = this;


        let start_str =
            this.current_start_date.format(
                'YYYY-MM-DD'
            );


        let week_label =
            `${this.current_start_date.format('MMM D')} - ${moment(this.current_start_date).add(6, 'days').format('MMM D, YYYY')}`;


        $('#week-date-range-heading').text(

            `${this.filter_shift || 'All Shifts'} · ${week_label}`

        );


        for (
            let i = 0;
            i < 7;
            i++
        ) {

            let d =
                moment(
                    this.current_start_date
                ).add(
                    i,
                    'days'
                );


            $(`#th-day-${i}`).text(
                `${d.format('ddd D')}`
            );

        }


        frappe.call({

            method:
                'care_management.care_management.page.support_task_schedule.support_task_schedule.get_week_tasks',


            args: {

                start_date:
                    start_str,

                participant:
                    me.filter_participant,

                category:
                    me.filter_category,

                shift:
                    me.filter_shift

            },


            callback:
                function(r) {

                    let occurrences =
                        r.message || [];


                    /*
                     * IMPORTANT:
                     *
                     * We also apply filtering in the browser.
                     *
                     * This means the UI remains filtered even if
                     * the current Python method returns more records
                     * than requested.
                     */
                    occurrences =
                        me.apply_schedule_filters(
                            occurrences
                        );


                    me.render_matrix_rows(
                        occurrences
                    );

                }

        });
    }


    // ================================================================
    // APPLY FILTERS
    // ================================================================

    apply_schedule_filters(
        occurrences
    ) {

        /*
         * IMPORTANT:
         * This was missing in the previous version.
         */
        let me = this;


        let participant =
            this.filter_participant;


        let participant_label =
            this.filter_participant_label;


        let category =
            this.filter_category;


        let shift =
            this.filter_shift;


        return (
            occurrences || []
        ).filter(
            function(occ) {


                // ----------------------------------------------------
                // PARTICIPANT
                // ----------------------------------------------------

                if (
                    participant
                ) {

                    let occurrence_participants = [

                        occ.participant,

                        occ.participant_name,

                        occ.participant_id,

                        occ.participant_display_name,

                        occ.customer_name

                    ]
                        .filter(
                            function(value) {

                                return (
                                    value !== undefined &&
                                    value !== null &&
                                    value !== ''
                                );

                            }
                        )
                        .map(
                            function(value) {

                                return String(
                                    value
                                ).trim();

                            }
                        );


                    let selected_participants = [

                        participant,

                        participant_label

                    ]
                        .filter(
                            function(value) {

                                return (
                                    value !== undefined &&
                                    value !== null &&
                                    value !== ''
                                );

                            }
                        )
                        .map(
                            function(value) {

                                return String(
                                    value
                                ).trim();

                            }
                        );


                    let participant_match =
                        occurrence_participants.some(
                            function(value) {

                                return selected_participants.includes(
                                    value
                                );

                            }
                        );


                    if (
                        !participant_match
                    ) {

                        return false;

                    }

                }


                // ----------------------------------------------------
                // CATEGORY
                // ----------------------------------------------------

                if (
                    category
                ) {

                    let occurrence_category =

                        occ.task_category ||

                        occ.category ||

                        '';


                    if (
                        String(
                            occurrence_category
                        ).trim() !==
                        String(
                            category
                        ).trim()
                    ) {

                        return false;

                    }

                }


                // ----------------------------------------------------
                // SHIFT
                // ----------------------------------------------------

                if (
                    shift
                ) {

                    let occurrence_shift =

                        occ.shift ||

                        occ.shift_type ||

                        '';


                    if (
                        String(
                            occurrence_shift
                        ).trim() !==
                        String(
                            shift
                        ).trim()
                    ) {

                        return false;

                    }

                }


                return true;

            }
        );
    }


    // ================================================================
    // TIME SORTING
    // ================================================================

    time_sort_key(
        occurrence
    ) {

        let mins =
            this.time_to_minutes(
                occurrence.scheduled_time
            );


        /*
         * Night Shift:
         *
         * 22:00
         * 23:00
         * 00:00
         * 01:00
         *
         * should remain chronological.
         */

        if (
            occurrence.shift ===
                'Night Shift' &&
            mins < 360
        ) {

            mins += 1440;

        }


        return mins;
    }


    time_to_minutes(
        time_str
    ) {

        let parts =
            (
                time_str ||
                '00:00:00'
            ).split(':');


        return (
            parseInt(
                parts[0],
                10
            ) * 60
        ) +
        parseInt(
            parts[1],
            10
        );
    }


    format_time_label(
        time_str
    ) {

        return moment(
            time_str,
            'HH:mm:ss'
        ).format(
            'h:mm A'
        );
    }


    // ================================================================
    // RENDER MATRIX
    // ================================================================

    render_matrix_rows(
        occurrences
    ) {

        let me = this;


        let tbody =
            $('#matrix-body');


        tbody.empty();


        let dated =
            occurrences.filter(
                function(o) {

                    return !o.is_floating;

                }
            );


        let floating =
            occurrences.filter(
                function(o) {

                    return !!o.is_floating;

                }
            );


        // ------------------------------------------------------------
        // UNIQUE TIMES
        // ------------------------------------------------------------

        let seen_times = {};


        dated.forEach(
            function(o) {

                seen_times[
                    o.scheduled_time
                ] = o;

            }
        );


        let time_rows =
            Object.values(
                seen_times
            ).sort(
                function(a, b) {

                    return (
                        me.time_sort_key(a) -
                        me.time_sort_key(b)
                    );

                }
            );


        // ------------------------------------------------------------
        // EMPTY STATE
        // ------------------------------------------------------------

        if (
            !time_rows.length &&
            !floating.length
        ) {

            tbody.append(`

                <tr>

                    <td
                        colspan="9"
                        style="
                            padding: 20px;
                            text-align: center;
                            color: #868e96;
                        "
                    >

                        No tasks scheduled for
                        ${me.filter_shift || 'this shift'}
                        in this week.

                    </td>

                </tr>

            `);


            return;
        }


        // ------------------------------------------------------------
        // DATED TASKS
        // ------------------------------------------------------------

        time_rows.forEach(
            function(row_ref) {

                let time_str =
                    row_ref.scheduled_time;


                let row_html = `

                    <tr
                        style="
                            border-bottom:
                                1px solid #e9ecef;
                        "
                    >

                        <td
                            style="
                                padding: 8px;
                                font-weight: bold;
                                background: #f8f9fa;
                                border-right:
                                    1px solid #d1d8dd;
                                text-align: center;
                            "
                        >

                            ${me.format_time_label(
                                time_str
                            )}

                        </td>

                `;


                for (
                    let i = 0;
                    i < 7;
                    i++
                ) {

                    let cell_tasks =
                        dated.filter(
                            function(t) {

                                return (
                                    t.scheduled_time ===
                                        time_str &&
                                    t.weekday_index ===
                                        i
                                );

                            }
                        );


                    row_html += `

                        <td
                            style="
                                padding: 6px;
                                border-right:
                                    1px solid #d1d8dd;
                                vertical-align:
                                    top;
                            "
                        >

                    `;


                    cell_tasks.forEach(
                        function(t) {

                            row_html +=
                                me.render_task_card(
                                    t
                                );

                        }
                    );


                    row_html += `
                        </td>
                    `;

                }


                row_html += `

                        <td
                            style="
                                padding: 6px;
                                background:
                                    #fffde7;
                            "
                        >
                        </td>

                    </tr>

                `;


                tbody.append(
                    row_html
                );

            }
        );


        // ------------------------------------------------------------
        // FLOATING TASKS
        // ------------------------------------------------------------

        if (
            floating.length
        ) {

            let row_html = `

                <tr
                    style="
                        border-bottom:
                            1px solid #e9ecef;
                    "
                >

                    <td
                        style="
                            padding: 8px;
                            font-weight: bold;
                            background: #f8f9fa;
                            border-right:
                                1px solid #d1d8dd;
                            text-align: center;
                        "
                    >
                        Anytime
                    </td>

            `;


            for (
                let i = 0;
                i < 7;
                i++
            ) {

                row_html += `

                    <td
                        style="
                            padding: 6px;
                            border-right:
                                1px solid #d1d8dd;
                        "
                    ></td>

                `;

            }


            row_html += `

                <td
                    style="
                        padding: 6px;
                        background:
                            #fffde7;
                        vertical-align:
                            top;
                    "
                >

            `;


            floating.forEach(
                function(t) {

                    row_html +=
                        me.render_task_card(t);

                }
            );


            row_html += `

                </td>

                </tr>

            `;


            tbody.append(
                row_html
            );

        }


        // ------------------------------------------------------------
        // TASK CARD CLICK
        // ------------------------------------------------------------

        $('.task-card-box').on('click', function() {
            $('.task-card-box').css('outline', 'none');
            $(this).css('outline', '2px solid #1c7ed6');

            let task_id = $(this).attr('data-id');
            let occurrence_date = $(this).attr('data-occurrence-date');

            me.selected_task_id = task_id;
            me.selected_occurrence_date =
                occurrence_date || moment().format('YYYY-MM-DD');

            me.load_inspector_details(task_id);
        });    
    }


    // ================================================================
    // TASK CARD
    // ================================================================

    render_task_card(
        task
    ) {

        let badge_class =
            task.clinical_priority ===
                'Critical'
                ? 'badge-danger'
                : 'badge-warning';


        let priority_badge = `

            <span
                class="badge ${badge_class}"
                style="float:right;"
            >
                ${task.clinical_priority || ''}
            </span>

        `;


        let background =
            task.is_floating
                ? '#fff3bf'
                : '#d0ebff';


        let border =
            task.is_floating
                ? '#fcc419'
                : '#74c0fc';


        return `
            <div class="task-card-box"
                data-id="${task.name}"
                data-occurrence-date="${task.occurrence_date || ''}"
                style="background: ${background}; border: 1px solid ${border}; padding: 8px; border-radius: 5px; margin-bottom: 6px; cursor: pointer;">
                <div style="font-weight: bold; color: #1864ab; font-size: 11px;">
                    [${task.participant || ''}] ${priority_badge}
                </div>
                <div style="color: #2b2b2b; font-size: 11px; margin-top:3px;">
                    ${task.task_name || ''}
                </div>
            </div>`;
    }


    // ================================================================
    // TASK INSPECTOR
    // ================================================================

    load_inspector_details(
        task_id
    ) {

        frappe.call({

            method:
                'frappe.client.get',

            args: {

                doctype:
                    'Support Task',

                name:
                    task_id

            },


            callback:
                function(r) {

                    let doc =
                        r.message;


                    if (!doc) {

                        return;

                    }


                    $('#inspector-title').text(

                        `Selected:
                        ${doc.task_name || ''}`

                    );


                    let details_html = `

                        <h6
                            style="
                                margin-top: 0;
                                color: #1864ab;
                            "
                        >
                            Task Overview
                        </h6>


                        <p
                            style="
                                margin: 3px 0;
                                font-size: 12px;
                            "
                        >

                            <strong>
                                Task Name:
                            </strong>

                            ${doc.task_name || ''}

                        </p>


                        <p
                            style="
                                margin: 3px 0;
                                font-size: 12px;
                            "
                        >

                            <strong>
                                Priority:
                            </strong>

                            ${doc.clinical_priority || ''}

                            |

                            <strong>
                                Category:
                            </strong>

                            ${doc.task_category || ''}

                        </p>


                        <p
                            style="
                                margin: 3px 0;
                                font-size: 12px;
                            "
                        >

                            <strong>
                                Description:
                            </strong>

                            ${doc.description || 'None'}

                        </p>


                        <p
                            style="
                                margin: 3px 0;
                                font-size: 12px;
                            "
                        >

                            <strong>
                                Staff Count Required:
                            </strong>

                            ${doc.staff_count_required || 0}

                        </p>

                    `;


                    $('#panel-left-details')
                        .html(
                            details_html
                        );

                }

        });
    }


    // ================================================================
    // RECORD DELIVERY
    // ================================================================

  show_outcome_dialog() {
            if (!this.selected_task_id) {
                frappe.msgprint(
                    'Please select a support task card first.'
                );
                return;
            }

            let me = this;

            let d = new frappe.ui.Dialog({
                title: 'Record Task Outcome',

                fields: [
                    {
                        label: 'Outcome',
                        fieldname: 'outcome',
                        fieldtype: 'Select',
                        options: [
                            'Completed',
                            'Partially Completed',
                            'Refused / Declined',
                            'Not Applicable',
                            'Cancelled'
                        ].join('\n'),
                        reqd: 1
                    },

                    {
                        label: 'Exception Type',
                        fieldname: 'exception_type',
                        fieldtype: 'Select',
                        options: [
                            '',
                            'Participant Unavailable',
                            'Participant Refused',
                            'Staff Unavailable',
                            'Unable to Complete',
                            'Safety Concern',
                            'Clinical Concern',
                            'Environmental Issue',
                            'Other'
                        ].join('\n')
                    },

                    {
                        label: 'Follow-up Required',
                        fieldname: 'follow_up_required',
                        fieldtype: 'Check'
                    },

                    {
                        label: 'Execution Notes / Outcome Details',
                        fieldname: 'execution_notes',
                        fieldtype: 'Small Text',
                        reqd: 1
                    }
                ],

                primary_action_label: 'Save Outcome',

                primary_action(values) {
                    frappe.call({
                        method:
                            'care_management.care_management.page.support_task_schedule.support_task_schedule.record_task_outcome',

                        args: {
                            task_id: me.selected_task_id,
                            scheduled_date: me.selected_occurrence_date,
                            outcome: values.outcome,
                            execution_notes: values.execution_notes,
                            exception_type: values.exception_type,
                            follow_up_required:
                                values.follow_up_required ? 1 : 0
                        },

                        callback: function(r) {
                            if (!r.message) {
                                return;
                            }

                            frappe.show_alert({
                                message:
                                    `Task recorded as ${r.message.outcome}.`,
                                indicator: 'green'
                            });

                            d.hide();

                            me.load_schedule_grid();
                            me.load_inspector_details(
                                me.selected_task_id
                            );
                        }
                    });
                }
            });

            d.show();
        }

    start_task_execution() {
        if (!this.selected_task_id) {
            frappe.msgprint(
                'Please select a support task card first.'
            );
            return;
        }

        let me = this;

        frappe.call({
            method:
                'care_management.care_management.page.support_task_schedule.support_task_schedule.start_task_execution',

            args: {
                task_id: me.selected_task_id,
                scheduled_date: me.selected_occurrence_date
            },

            callback: function(r) {
                if (!r.message) {
                    return;
                }

                if (r.message.status === 'already_completed') {
                    frappe.msgprint(
                        `This task has already been completed with outcome:
                        <b>${r.message.outcome}</b>`
                    );
                    return;
                }

                frappe.show_alert({
                    message: 'Task started.',
                    indicator: 'blue'
                });

                me.load_schedule_grid();
                me.load_inspector_details(me.selected_task_id);
            }
        });
    }
    // ================================================================
    // LOG MISSED TASK
    // ================================================================

    show_missed_dialog() {

        if (
            !this.selected_task_id
        ) {

            frappe.msgprint(
                'Please select a support task card from the matrix grid first.'
            );

            return;
        }


        let me = this;


        let d =
            new frappe.ui.Dialog({

                title:
                    'Log Task as Missed / Omission',


                fields: [

                    {
                        label:
                            'Omission Reason Category',

                        fieldname:
                            'reason_category',

                        fieldtype:
                            'Select',

                        options:
                            '\nParticipant Refused\nParticipant Hospitalized / Absent\nStock / Medication Unavailable\nClinical Risk / Adverse Reaction\nStaff Shortage\nOther',

                        reqd:
                            1
                    },


                    {
                        label:
                            'Omission Clinical Justification',

                        fieldname:
                            'omission_notes',

                        fieldtype:
                            'Small Text',

                        reqd:
                            1
                    },


                    {
                        label:
                            'Escalate as Incident Report',

                        fieldname:
                            'incident_escalated',

                        fieldtype:
                            'Check'
                    }

                ],


                primary_action_label:
                    'Submit Omission',


                primary_action:
                    function(values) {

                        frappe.call({
                            method:
                                'care_management.care_management.page.support_task_schedule.support_task_schedule.record_task_outcome',

                            args: {
                                task_id: me.selected_task_id,
                                scheduled_date: me.selected_occurrence_date,
                                outcome: 'Missed',
                                execution_notes: values.omission_notes,
                                exception_type: values.reason_category,
                                follow_up_required: 0
                            },

                            callback: function(r) {
                                if (!r.message) {
                                    return;
                                }

                                frappe.show_alert({
                                    message: 'Task omission recorded.',
                                    indicator: 'orange'
                                });

                                d.hide();

                                me.load_schedule_grid();
                                me.load_inspector_details(
                                    me.selected_task_id
                                );
                            }
                        });

                    }

            });


        d.show();
    }

        // ================================================================
    // PHASE 3B - MANAGER REVIEW
    // ================================================================

    initialize_manager_review() {

        let me = this;

        /*
         * Manager Review is intentionally initialized separately
         * from the operational scheduler so the existing scheduler
         * remains unchanged.
         */

        let today =
            moment().format('YYYY-MM-DD');

        $('#manager-review-start-date')
            .val(today);

        $('#manager-review-end-date')
            .val(today);

        $('#btn-apply-manager-review')
            .on(
                'click',
                function() {
                    me.load_manager_review();
                }
            );

        $('#btn-refresh-manager-review')
            .on(
                'click',
                function() {
                    me.load_manager_review();
                }
            );

        this.load_manager_review();
    }


    // ================================================================
    // LOAD MANAGER REVIEW
    // ================================================================

    load_manager_review() {

        let me = this;

        let start_date =
            $('#manager-review-start-date').val();

        let end_date =
            $('#manager-review-end-date').val();

        let status =
            $('#manager-review-status').val();


        if (
            !start_date ||
            !end_date
        ) {

            $('#manager-review-results').html(`
                <div
                    class="text-muted"
                    style="
                        padding: 20px;
                        text-align: center;
                    "
                >
                    Please select a start and end date.
                </div>
            `);

            return;
        }


        if (
            start_date > end_date
        ) {

            frappe.msgprint(
                'Start Date cannot be after End Date.'
            );

            return;
        }


        $('#manager-review-results').html(`
            <div
                class="text-muted"
                style="
                    padding: 20px;
                    text-align: center;
                "
            >
                <i class="fa fa-spinner fa-spin"></i>
                Loading manager review...
            </div>
        `);


        frappe.call({

            method:
                'care_management.care_management.page.support_task_schedule.support_task_schedule.get_manager_review_tasks',

            args: {

                start_date:
                    start_date,

                end_date:
                    end_date,

                status:
                    status || null

            },

            callback:
                function(r) {

                    if (
                        r.exc
                    ) {

                        $('#manager-review-results').html(`
                            <div
                                class="text-danger"
                                style="
                                    padding: 20px;
                                    text-align: center;
                                "
                            >
                                Unable to load manager review.
                            </div>
                        `);

                        return;
                    }


                    let results =
                        r.message || [];


                    me.render_manager_review_summary(
                        results
                    );


                    me.render_manager_review_results(
                        results
                    );
                }
        });
    }


    // ================================================================
    // MANAGER REVIEW SUMMARY
    // ================================================================

    render_manager_review_summary(
        results
    ) {

        let completed = 0;
        let exceptions = 0;
        let missed = 0;
        let follow_up = 0;
        let in_progress = 0;
        let cancelled = 0;


        (results || []).forEach(
            function(row) {

                let category =
                    row.review_category ||
                    '';


                if (
                    category === 'Completed'
                ) {
                    completed++;
                }


                if (
                    category === 'Exception'
                ) {
                    exceptions++;
                }


                if (
                    category === 'Missed'
                ) {
                    missed++;
                }


                if (
                    category === 'Follow-up'
                ) {
                    follow_up++;
                }


                if (
                    category === 'In Progress'
                ) {
                    in_progress++;
                }


                if (
                    category === 'Cancelled'
                ) {
                    cancelled++;
                }

            }
        );


        $('#manager-review-summary').html(`

            <div
                style="
                    display: flex;
                    gap: 8px;
                    flex-wrap: wrap;
                "
            >

                <span class="indicator-pill">
                    Completed: ${completed}
                </span>

                <span class="indicator-pill">
                    Exceptions: ${exceptions}
                </span>

                <span class="indicator-pill">
                    Missed: ${missed}
                </span>

                <span class="indicator-pill">
                    Follow-up: ${follow_up}
                </span>

                <span class="indicator-pill">
                    In Progress: ${in_progress}
                </span>

                <span class="indicator-pill">
                    Cancelled: ${cancelled}
                </span>

            </div>

        `);
    }


    // ================================================================
    // MANAGER REVIEW RESULTS
    // ================================================================

    render_manager_review_results(
        results
    ) {

        let me = this;

        let container =
            $('#manager-review-results');


        results =
            results || [];


        if (
            !results.length
        ) {

            container.html(`
                <div
                    class="text-muted"
                    style="
                        padding: 30px;
                        text-align: center;
                        border: 1px dashed #ced4da;
                        border-radius: 6px;
                    "
                >
                    No execution records found
                    for the selected filters.
                </div>
            `);

            return;
        }


        /*
         * Priority ordering:
         *
         * High
         * Medium
         * Low
         */

        let priority_order = {

            'High': 1,
            'Medium': 2,
            'Low': 3

        };


        results.sort(
            function(a, b) {

                let a_priority =
                    priority_order[
                        a.review_priority
                    ] || 99;

                let b_priority =
                    priority_order[
                        b.review_priority
                    ] || 99;


                return (
                    a_priority -
                    b_priority
                );
            }
        );


        let html = '';


        results.forEach(
            function(row) {

                let priority =
                    row.review_priority ||
                    'Low';


                let priority_label =
                    priority === 'High'
                        ? 'HIGH'
                        : priority === 'Medium'
                            ? 'MEDIUM'
                            : 'NORMAL';


                let priority_class =
                    priority === 'High'
                        ? 'text-danger'
                        : priority === 'Medium'
                            ? 'text-warning'
                            : 'text-muted';


                let execution_instance =
                    frappe.utils.escape_html(
                        row.execution_instance ||
                        ''
                    );


                let support_task =
                    frappe.utils.escape_html(
                        row.support_task ||
                        ''
                    );


                let participant =
                    frappe.utils.escape_html(
                        row.participant ||
                        'Participant not set'
                    );


                let task_name =
                    frappe.utils.escape_html(
                        row.task_name ||
                        'Support Task'
                    );


                let scheduled_date =
                    frappe.utils.escape_html(
                        row.scheduled_date ||
                        '-'
                    );


                let scheduled_time =
                    frappe.utils.escape_html(
                        row.scheduled_time ||
                        ''
                    );


                let status =
                    frappe.utils.escape_html(
                        row.status ||
                        '-'
                    );


                let category =
                    frappe.utils.escape_html(
                        row.review_category ||
                        '-'
                    );


                let exception_type =
                    frappe.utils.escape_html(
                        row.exception_type ||
                        ''
                    );


                let review_follow_up =
                    row.follow_up_required
                        ? 'Required'
                        : 'No';


                html += `

                    <div
                        class="manager-review-card"
                        data-execution-instance="${execution_instance}"
                        style="
                            border: 1px solid #d9d9d9;
                            border-radius: 6px;
                            padding: 12px;
                            margin-bottom: 8px;
                            background: #fff;
                            cursor: pointer;
                        "
                    >

                        <div
                            style="
                                display: flex;
                                justify-content:
                                    space-between;
                                align-items:
                                    center;
                                gap: 10px;
                            "
                        >

                            <div>

                                <div
                                    style="
                                        font-weight: 700;
                                        font-size: 13px;
                                    "
                                >
                                    ${task_name}
                                </div>

                                <div
                                    style="
                                        font-size: 11px;
                                        color: #6c757d;
                                        margin-top: 3px;
                                    "
                                >
                                    ${participant}
                                </div>

                            </div>


                            <div
                                class="${priority_class}"
                                style="
                                    font-weight: 700;
                                    font-size: 11px;
                                "
                            >
                                ${priority_label}
                            </div>

                        </div>


                        <div
                            style="
                                display: grid;
                                grid-template-columns:
                                    repeat(
                                        auto-fit,
                                        minmax(160px, 1fr)
                                    );
                                gap: 8px 16px;
                                margin-top: 10px;
                                font-size: 11px;
                            "
                        >

                            <div>

                                <strong>
                                    Execution:
                                </strong>

                                ${execution_instance}

                            </div>


                            <div>

                                <strong>
                                    Support Task:
                                </strong>

                                ${support_task}

                            </div>


                            <div>

                                <strong>
                                    Date:
                                </strong>

                                ${scheduled_date}

                            </div>


                            <div>

                                <strong>
                                    Time:
                                </strong>

                                ${scheduled_time || '-'}

                            </div>


                            <div>

                                <strong>
                                    Status:
                                </strong>

                                ${status}

                            </div>


                            <div>

                                <strong>
                                    Category:
                                </strong>

                                ${category}

                            </div>


                            <div>

                                <strong>
                                    Follow-up:
                                </strong>

                                ${review_follow_up}

                            </div>

                        </div>


                        ${
                            exception_type
                                ? `
                                    <div
                                        style="
                                            margin-top: 8px;
                                            padding: 8px;
                                            border-radius: 4px;
                                            background: #fff5f5;
                                            font-size: 11px;
                                        "
                                    >

                                        <strong>
                                            Exception:
                                        </strong>

                                        ${exception_type}

                                    </div>
                                `
                                : ''
                        }

                    </div>

                `;
            }
        );


        container.html(
            html
        );


        /*
         * Phase 3B currently opens a lightweight review message.
         *
         * Phase 3C will replace this with the full
         * Execution Review panel.
         */

        $('.manager-review-card')
            .on(
                'click',
                function() {

                    let execution =
                        $(this)
                            .attr(
                                'data-execution-instance'
                            );


                    if (
                        !execution
                    ) {
                        return;
                    }


                    frappe.msgprint({

                        title:
                            'Execution Review',

                        message:
                            `
                            <div>

                                <p>
                                    <strong>
                                        Execution Instance:
                                    </strong>

                                    ${frappe.utils.escape_html(
                                        execution
                                    )}
                                </p>

                                <p>
                                    This execution is ready
                                    for manager review.
                                </p>

                            </div>
                            `,

                        indicator:
                            'blue'

                    });

                }
            );
    }

}