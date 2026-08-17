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
        this.current_start_date = moment().startOf('isoWeek');
        this.selected_task_id = null;
        this.selected_occurrence_date = null;

        this.filter_participant = null;
        this.filter_participant_label = null;
        this.filter_category = null;
        this.filter_shift = this.get_current_shift();

        this.tracker_config = {
            'Mood Tracker': 'Mood Tracker Entry',
            'Sleep Tracker': 'Sleep Tracker Entry',
            'Shower Chart': 'Shower Chart Item',
            'Daily Bowel Record Chart': 'Daily Bowel Record Item',
            'Fluid Intake Output Chart': 'Fluid Intake Item',
            'Weekly Exercise Record': 'Exercise Record Item',
            'Seizure Chart': 'Seizure Chart Entry'
        };

        this.make_layout();
        this.load_schedule_grid();
    }

    // ================================================================
    // CURRENT SHIFT
    // ================================================================
    get_current_shift() {
        let mins = moment().hours() * 60 + moment().minutes();
        if (mins >= 6 * 60 && mins < 14 * 60) return 'AM Shift';
        if (mins >= 14 * 60 && mins < 22 * 60) return 'PM Shift';
        return 'Night Shift';
    }

    // ================================================================
    // PAGE LAYOUT
    // ================================================================
    make_layout() {
        let me = this;

        // Navigation Actions
        this.page.set_secondary_action('Previous Week', function() {
            me.current_start_date.subtract(7, 'days');
            me.load_schedule_grid();
        });

        this.page.set_primary_action('Next Week', function() {
            me.current_start_date.add(7, 'days');
            me.load_schedule_grid();
        });

        let html = `
            <style>
                .scheduler-dashboard {
                    padding: 14px 12px 36px 12px;
                    background: radial-gradient(circle at 10% 10%, rgba(241, 245, 249, 0.8) 0%, rgba(248, 250, 252, 0.6) 100%);
                    font-family: inherit;
                    color: #0f172a;
                }

                /* GLASS HEADER */
                .scheduler-header-bar {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    background: rgba(255, 255, 255, 0.82);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    padding: 14px 18px;
                    border-radius: 14px;
                    margin-bottom: 16px;
                    border: 1px solid rgba(203, 213, 225, 0.8);
                    box-shadow: 0 4px 15px rgba(15, 23, 42, 0.03);
                }

                .scheduler-header-title {
                    font-weight: 800;
                    color: #0f2744;
                    font-size: 15px;
                    letter-spacing: -0.01em;
                }

                .scheduler-shift-badge {
                    background: linear-gradient(135deg, #0f2744 0%, #1e3a5f 100%);
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 5px 12px;
                    border-radius: 20px;
                    box-shadow: 0 2px 6px rgba(15, 39, 68, 0.2);
                }

                /* GLASS FILTER BAR */
                #support-task-filter-bar {
                    display: flex;
                    gap: 14px;
                    align-items: flex-end;
                    flex-wrap: wrap;
                    padding: 16px 18px;
                    margin-bottom: 18px;
                    background: rgba(255, 255, 255, 0.82);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    border: 1px solid rgba(203, 213, 225, 0.8);
                    border-radius: 14px;
                    position: relative;
                    z-index: 1001;
                    box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.04);
                }

                .scheduler-filter-item {
                    display: flex;
                    flex-direction: column;
                    justify-content: flex-end;
                }

                .scheduler-filter-label {
                    display: block;
                    font-size: 11px;
                    font-weight: 700;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                    color: #1e3a5f;
                    margin-bottom: 6px;
                    height: 14px;
                    line-height: 14px;
                }

                #support-task-filter-bar .form-control,
                #support-task-filter-bar select {
                    height: 34px !important;
                    min-height: 34px !important;
                    border-radius: 8px !important;
                    border: 1px solid #cbd5e1 !important;
                    background: rgba(255, 255, 255, 0.95) !important;
                    font-size: 12px !important;
                    box-shadow: none !important;
                    padding: 4px 10px !important;
                    color: #0f172a !important;
                }

                #participant-filter-container .frappe-control,
                #category-filter-container .frappe-control,
                #shift-filter-container .frappe-control {
                    margin-bottom: 0px !important;
                }

                #participant-filter-container .control-label,
                #category-filter-container .control-label,
                #shift-filter-container .control-label {
                    display: none !important;
                }

                #support-task-filter-bar .awesomplete {
                    position: relative;
                    z-index: 1005;
                }

                #support-task-filter-bar .awesomplete > ul {
                    z-index: 1005 !important;
                    border-radius: 8px !important;
                    box-shadow: 0 10px 25px rgba(15, 23, 42, 0.15) !important;
                    border: 1px solid #cbd5e1 !important;
                }

                /* MATRIX TABLE CONTAINER */
                .matrix-table-container {
                    border: 1px solid rgba(203, 213, 225, 0.85);
                    border-radius: 14px;
                    background: rgba(255, 255, 255, 0.75);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
                    overflow: hidden;
                    position: relative;
                    z-index: 1;
                }

                .matrix-table {
                    width: 100%;
                    min-width: 900px;
                    border-collapse: collapse;
                    text-align: left;
                    font-size: 12px;
                }

                .matrix-table thead tr {
                    background: rgba(241, 245, 249, 0.9);
                    border-bottom: 1px solid #cbd5e1;
                    text-align: center;
                }

                .matrix-table th {
                    padding: 12px 10px;
                    border-right: 1px solid #e2e8f0;
                    color: #0f2744;
                    font-weight: 700;
                    letter-spacing: 0.01em;
                }

                .matrix-table th.th-time {
                    width: 95px;
                    background: #f8fafc;
                }

                .matrix-table th.th-floating {
                    background: rgba(254, 252, 232, 0.95);
                    color: #854d0e;
                }

                .matrix-table td {
                    padding: 8px 6px;
                    border-right: 1px solid #e2e8f0;
                    border-bottom: 1px solid #e2e8f0;
                    vertical-align: top;
                }

                .matrix-table td.td-time {
                    font-weight: 700;
                    background: rgba(248, 250, 252, 0.85);
                    color: #1e3a5f;
                    text-align: center;
                    font-size: 11.5px;
                }

                .matrix-table td.td-floating {
                    background: rgba(254, 252, 232, 0.4);
                }

                /* TASK CARDS */
                .task-card-box {
                    border-radius: 8px;
                    padding: 9px 10px;
                    margin-bottom: 6px;
                    cursor: pointer;
                    transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
                    touch-action: manipulation;
                    -webkit-tap-highlight-color: transparent;
                }

                .task-card-box:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
                }

                .task-card-box:active {
                    transform: scale(0.97);
                }

                .task-card-standard {
                    background: rgba(240, 249, 255, 0.85);
                    border: 1px solid rgba(186, 230, 253, 0.9);
                }

                .task-card-floating {
                    background: rgba(254, 252, 232, 0.9);
                    border: 1px solid rgba(253, 230, 138, 0.9);
                }

                .task-card-title {
                    font-weight: 700;
                    color: #0f2744;
                    font-size: 11px;
                }

                .task-card-name {
                    color: #334155;
                    font-size: 11px;
                    margin-top: 3px;
                    line-height: 1.35;
                }

                /* PRIORITY PILLS */
                .task-badge {
                    display: inline-block;
                    float: right;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-size: 9.5px;
                    font-weight: 700;
                    letter-spacing: 0.02em;
                }

                .task-badge-critical {
                    background: #fee2e2;
                    color: #991b1b;
                }

                .task-badge-warning {
                    background: #fef3c7;
                    color: #92400e;
                }

                /* TASK INSPECTOR PANEL */
                .inspector-panel {
                    margin-top: 18px;
                    border: 1px solid rgba(203, 213, 225, 0.8);
                    border-radius: 14px;
                    background: rgba(255, 255, 255, 0.8);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
                    overflow: hidden;
                    position: relative;
                    z-index: 1;
                }

                .inspector-header {
                    background: rgba(248, 250, 252, 0.75);
                    padding: 14px 18px;
                    border-bottom: 1px solid rgba(203, 213, 225, 0.8);
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    flex-wrap: wrap;
                    gap: 12px;
                }

                .inspector-title {
                    font-weight: 800;
                    color: #0f2744;
                    font-size: 14px;
                }

                /* TOUCH ACTION BUTTONS */
                .btn-action-touch {
                    height: 32px;
                    padding: 0 12px;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 11.5px;
                    display: inline-flex;
                    align-items: center;
                    gap: 6px;
                    transition: all 0.2s ease;
                    border: none;
                }

                .btn-action-touch:hover {
                    transform: translateY(-1px);
                }

                .btn-task-navy {
                    background: linear-gradient(135deg, #0f2744 0%, #1e3a5f 100%);
                    color: #ffffff !important;
                    box-shadow: 0 3px 8px rgba(15, 39, 68, 0.2);
                }

                .btn-task-green {
                    background: linear-gradient(135deg, #059669 0%, #10b981 100%);
                    color: #ffffff !important;
                    box-shadow: 0 3px 8px rgba(16, 185, 129, 0.2);
                }

                .btn-task-amber {
                    background: linear-gradient(135deg, #d97706 0%, #f59e0b 100%);
                    color: #ffffff !important;
                    box-shadow: 0 3px 8px rgba(245, 158, 11, 0.2);
                }

                .btn-task-slate {
                    background: #f1f5f9;
                    color: #334155 !important;
                    border: 1px solid #cbd5e1;
                }

                .btn-task-slate:hover {
                    background: #e2e8f0;
                    color: #0f2744 !important;
                }

                .inspector-content-box {
                    padding: 16px;
                }

                .details-callout {
                    background: rgba(240, 249, 255, 0.7);
                    border: 1px solid rgba(186, 230, 253, 0.8);
                    padding: 16px;
                    border-radius: 10px;
                }

                .details-subheading {
                    color: #0f2744;
                    border-bottom: 1px solid #bae6fd;
                    padding-bottom: 6px;
                    margin-top: 14px;
                    margin-bottom: 10px;
                    font-size: 12px;
                    font-weight: 700;
                    text-transform: uppercase;
                    letter-spacing: 0.03em;
                }

                .details-subheading:first-of-type {
                    margin-top: 0;
                }

                @media (max-width: 768px) {
                    .matrix-table-container { overflow-x: auto; }
                    .inspector-flex { flex-direction: column !important; }
                    .btn-action-touch { width: 100%; min-height: 40px; justify-content: center; margin-bottom: 4px; }
                    #support-task-filter-bar { flex-direction: column; align-items: stretch !important; }
                    #participant-filter-container, #category-filter-container, #shift-filter-container { min-width: 100% !important; width: 100%; }
                }
            </style>

            <div class="scheduler-dashboard">
                <!-- HEADER BAR -->
                <div class="scheduler-header-bar">
                    <div id="week-date-range-heading" class="scheduler-header-title">Week View</div>
                    <div>
                        <span class="scheduler-shift-badge">
                            <i class="fa fa-clock-o" style="margin-right: 4px;"></i> Frontline Shift Board
                        </span>
                    </div>
                </div>

                <!-- FILTER BAR -->
                <div id="support-task-filter-bar">
                    <div id="participant-filter-container" class="scheduler-filter-item" style="min-width: 240px; flex: 1;">
                        <label class="scheduler-filter-label">Participant</label>
                    </div>
                    <div id="category-filter-container" class="scheduler-filter-item" style="min-width: 200px;">
                        <label class="scheduler-filter-label">Category</label>
                    </div>
                    <div id="shift-filter-container" class="scheduler-filter-item" style="min-width: 180px;">
                        <label class="scheduler-filter-label">Shift</label>
                    </div>
                </div>

                <!-- MATRIX TABLE -->
                <div class="matrix-table-container">
                    <table class="matrix-table">
                        <thead>
                            <tr>
                                <th class="th-time">Time</th>
                                <th id="th-day-0">Mon</th>
                                <th id="th-day-1">Tue</th>
                                <th id="th-day-2">Wed</th>
                                <th id="th-day-3">Thu</th>
                                <th id="th-day-4">Fri</th>
                                <th id="th-day-5">Sat</th>
                                <th id="th-day-6">Sun</th>
                                <th class="th-floating">Floating Tasks</th>
                            </tr>
                        </thead>
                        <tbody id="matrix-body"></tbody>
                    </table>
                </div>

                <!-- TASK INSPECTOR -->
                <div class="inspector-panel">
                    <div class="inspector-header">
                        <div id="inspector-title" class="inspector-title">Task Inspector Panel</div>
                        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                            <button class="btn btn-action-touch btn-task-navy" id="btn-start-task">
                                <i class="fa fa-play"></i> Start Task
                            </button>
                            <button class="btn btn-action-touch btn-task-green" id="btn-record-outcome">
                                <i class="fa fa-check"></i> Record Outcome
                            </button>
                            <button class="btn btn-action-touch btn-task-amber" id="btn-log-missed">
                                <i class="fa fa-exclamation-triangle"></i> Log Missed
                            </button>
                            <button class="btn btn-action-touch btn-task-slate" id="btn-fill-tracker">
                                <i class="fa fa-list-alt"></i> Fill Tracker
                            </button>
                        </div>
                    </div>

                    <div id="inspector-content" class="inspector-content-box">
                        <div id="panel-left-details" class="details-callout">
                            <p style="margin: 4px 0; color: #64748b;">
                                <em>Tap any task card above to inspect instructions and record outcome.</em>
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        `;

        $(this.page.body).html(html);

        // ============================================================
        // PARTICIPANT FILTER
        // ============================================================
        let participant_filter = frappe.ui.form.make_control({
            parent: $('#participant-filter-container'),
            df: {
                fieldname: 'participant_filter',
                label: 'Participant',
                fieldtype: 'Link',
                options: 'Participant Profile',
                change: function() {
                    me.filter_participant = this.get_value() || null;
                    me.filter_participant_label = this.get_input_value ? this.get_input_value() : null;
                    me.load_schedule_grid();
                }
            },
            render_input: true
        });

        participant_filter.set_value(this.filter_participant || '');

        // ============================================================
        // CATEGORY FILTER
        // ============================================================
        frappe.model.with_doctype('Support Task', function() {
            let task_meta = frappe.get_meta('Support Task');
            let category_df = task_meta && task_meta.fields
                ? task_meta.fields.find(function(df) { return df.fieldname === 'task_category'; })
                : null;

            let category_options = [];
            if (category_df && category_df.options) {
                category_options = String(category_df.options)
                    .split('\n')
                    .map(function(value) { return value.trim(); })
                    .filter(function(value) { return value !== ''; });
            }

            let category_filter = frappe.ui.form.make_control({
                parent: $('#category-filter-container'),
                df: {
                    fieldname: 'category_filter',
                    label: 'Category',
                    fieldtype: 'Select',
                    options: [''].concat(category_options).join('\n'),
                    change: function() {
                        me.filter_category = this.get_value() || null;
                        me.load_schedule_grid();
                    }
                },
                render_input: true
            });

            category_filter.set_value(me.filter_category || '');
        });

        // ============================================================
        // SHIFT FILTER
        // ============================================================
        let shift_filter = frappe.ui.form.make_control({
            parent: $('#shift-filter-container'),
            df: {
                fieldname: 'shift_filter',
                label: 'Shift',
                fieldtype: 'Select',
                options: 'AM Shift\nPM Shift\nNight Shift',
                default: this.filter_shift,
                change: function() {
                    me.filter_shift = this.get_value() || null;
                    me.load_schedule_grid();
                }
            },
            render_input: true
        });

        shift_filter.set_value(this.filter_shift || this.get_current_shift());
        this.filter_shift = shift_filter.get_value() || this.get_current_shift();

        // ============================================================
        // BUTTON EVENTS
        // ============================================================
        $('#btn-start-task').on('click', function() { me.start_task_execution(); });
        $('#btn-record-outcome').on('click', function() { me.show_outcome_dialog(); });
        $('#btn-log-missed').on('click', function() { me.show_missed_dialog(); });
        $('#btn-fill-tracker').on('click', function() { me.show_tracker_picker(); });

        $(document).on('click', '.staff-plan-view-btn', function() {
            const doctype = $(this).attr('data-doctype');
            const name = $(this).attr('data-name');
            if (!doctype || !name) {
                frappe.msgprint('Source plan information is unavailable.');
                return;
            }
            frappe.set_route('Form', doctype, name);
        });

        $(document).on('click', '.critical-care-plan-btn', function() {
            const doctype = $(this).attr('data-doctype');
            const name = $(this).attr('data-name');
            if (!doctype || !name) {
                frappe.msgprint('Care plan information is unavailable.');
                return;
            }
            frappe.set_route('Form', doctype, name);
        });
    }

    // ================================================================
    // TRACKER PICKER
    // ================================================================
    show_tracker_picker() {
        let me = this;
        let picker = new frappe.ui.Dialog({
            title: 'Fill Tracker Chart',
            fields: [
                {
                    label: 'Participant',
                    fieldname: 'participant',
                    fieldtype: 'Link',
                    options: 'Participant Profile',
                    reqd: 1,
                    default: me.filter_participant || ''
                },
                {
                    label: 'Tracker / Chart',
                    fieldname: 'tracker_doctype',
                    fieldtype: 'Select',
                    options: Object.keys(me.tracker_config).join('\n'),
                    reqd: 1
                }
            ],
            primary_action_label: 'Open Grid',
            primary_action: function(values) {
                if (!values.participant) {
                    frappe.msgprint('Please select a Participant.');
                    return;
                }
                if (!values.tracker_doctype) {
                    frappe.msgprint('Please select a Tracker / Chart.');
                    return;
                }
                picker.hide();
                setTimeout(function() {
                    me.show_tracker_matrix_dialog(values.participant, values.tracker_doctype);
                }, 200);
            }
        });
        picker.show();
    }

    // ================================================================
    // TRACKER GRID
    // ================================================================
    show_tracker_matrix_dialog(participant, tracker_doctype) {
        let item_doctype = this.tracker_config[tracker_doctype];
        if (!item_doctype) {
            frappe.msgprint(`No tracker configuration found for ${tracker_doctype}.`);
            return;
        }

        frappe.model.with_doctype(item_doctype, function() {
            let meta = frappe.get_meta(item_doctype);
            if (!meta || !meta.fields) {
                frappe.msgprint(`Unable to load DocType metadata for ${item_doctype}.`);
                return;
            }

            let usable_fields = meta.fields.filter(function(df) {
                return !['Section Break', 'Column Break', 'Tab Break', 'HTML', 'Button'].includes(df.fieldtype);
            });

            let grid_fields = usable_fields
                .filter(function(df) { return df.in_list_view || df.reqd; })
                .map(function(df) {
                    let field = {
                        fieldname: df.fieldname,
                        label: df.label || df.fieldname,
                        fieldtype: df.fieldtype,
                        in_list_view: 1,
                        reqd: df.reqd ? 1 : 0
                    };
                    if (df.options) field.options = df.options;
                    if (df.default !== undefined) field.default = df.default;
                    if (df.read_only) field.read_only = 1;
                    if (df.description) field.description = df.description;
                    if (df.precision) field.precision = df.precision;
                    return field;
                });

            if (!grid_fields.length) {
                grid_fields = usable_fields.map(function(df) {
                    let field = {
                        fieldname: df.fieldname,
                        label: df.label || df.fieldname,
                        fieldtype: df.fieldtype,
                        in_list_view: 1,
                        reqd: df.reqd ? 1 : 0
                    };
                    if (df.options) field.options = df.options;
                    if (df.default !== undefined) field.default = df.default;
                    return field;
                });
            }

            if (!grid_fields.length) {
                frappe.msgprint(`No usable fields were found in ${item_doctype}.`);
                return;
            }

            let d = new frappe.ui.Dialog({
                title: `${tracker_doctype} - Matrix Entry (${participant})`,
                size: 'extra-large',
                fields: [
                    {
                        label: 'Entries',
                        fieldname: 'entries',
                        fieldtype: 'Table',
                        fields: grid_fields,
                        in_place_edit: true,
                        cannot_add_rows: false,
                        cannot_delete_rows: false
                    }
                ],
                primary_action_label: 'Save Entries',
                primary_action: function(values) {
                    let rows = values.entries || [];
                    if (!rows.length) {
                        frappe.msgprint('Add at least one row to the grid before saving.');
                        return;
                    }

                    rows = rows.map(function(row) {
                        let clean = Object.assign({}, row);
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
                    });

                    frappe.call({
                        method: 'care_management.care_management.page.support_task_schedule.support_task_schedule.save_tracker_matrix_entries',
                        args: {
                            participant: participant,
                            tracker_doctype: tracker_doctype,
                            rows: rows
                        },
                        freeze: true,
                        freeze_message: 'Saving tracker entries...',
                        callback: function(r) {
                            if (r.message && r.message.status === 'success') {
                                frappe.show_alert({
                                    message: `${r.message.rows_saved} entr${r.message.rows_saved === 1 ? 'y' : 'ies'} saved to ${tracker_doctype}.`,
                                    indicator: 'green'
                                });
                                d.hide();
                            } else {
                                frappe.msgprint({
                                    title: 'Save Failed',
                                    message: (r.message && r.message.message) ? r.message.message : 'Unable to save tracker entries.',
                                    indicator: 'red'
                                });
                            }
                        },
                        error: function() {
                            frappe.msgprint({
                                title: 'Error',
                                message: 'An error occurred while saving tracker entries.',
                                indicator: 'red'
                            });
                        }
                    });
                }
            });

            d.show();
        });
    }

    // ================================================================
    // LOAD SCHEDULE
    // ================================================================
    load_schedule_grid() {
        let me = this;
        let start_str = this.current_start_date.format('YYYY-MM-DD');
        let week_label = `${this.current_start_date.format('MMM D')} - ${moment(this.current_start_date).add(6, 'days').format('MMM D, YYYY')}`;

        $('#week-date-range-heading').text(`${this.filter_shift || 'All Shifts'} · ${week_label}`);

        for (let i = 0; i < 7; i++) {
            let d = moment(this.current_start_date).add(i, 'days');
            $(`#th-day-${i}`).text(`${d.format('ddd D')}`);
        }

        frappe.call({
            method: 'care_management.care_management.page.support_task_schedule.support_task_schedule.get_week_tasks',
            args: {
                start_date: start_str,
                participant: me.filter_participant,
                category: me.filter_category,
                shift: me.filter_shift
            },
            callback: function(r) {
                let occurrences = r.message || [];
                occurrences = me.apply_schedule_filters(occurrences);
                me.render_matrix_rows(occurrences);
            }
        });
    }

    // ================================================================
    // APPLY FILTERS
    // ================================================================
    apply_schedule_filters(occurrences) {
        let participant = this.filter_participant;
        let participant_label = this.filter_participant_label;
        let category = this.filter_category;
        let shift = this.filter_shift;

        return (occurrences || []).filter(function(occ) {
            // Participant match
            if (participant) {
                let occurrence_participants = [
                    occ.participant,
                    occ.participant_name,
                    occ.participant_id,
                    occ.participant_display_name,
                    occ.customer_name
                ].filter(function(value) {
                    return value !== undefined && value !== null && value !== '';
                }).map(function(value) {
                    return String(value).trim();
                });

                let selected_participants = [participant, participant_label].filter(function(value) {
                    return value !== undefined && value !== null && value !== '';
                }).map(function(value) {
                    return String(value).trim();
                });

                let participant_match = occurrence_participants.some(function(value) {
                    return selected_participants.includes(value);
                });

                if (!participant_match) return false;
            }

            // Category match
            if (category) {
                let occurrence_category = occ.task_category || occ.category || '';
                if (String(occurrence_category).trim() !== String(category).trim()) return false;
            }

            // Shift match
            if (shift) {
                let occurrence_shift = occ.shift || occ.shift_type || '';
                if (String(occurrence_shift).trim() !== String(shift).trim()) return false;
            }

            return true;
        });
    }

    // ================================================================
    // TIME SORTING
    // ================================================================
    time_sort_key(occurrence) {
        let mins = this.time_to_minutes(occurrence.scheduled_time);
        if (occurrence.shift === 'Night Shift' && mins < 360) {
            mins += 1440;
        }
        return mins;
    }

    time_to_minutes(time_str) {
        let parts = (time_str || '00:00:00').split(':');
        return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
    }

    format_time_label(time_str) {
        return moment(time_str, 'HH:mm:ss').format('h:mm A');
    }

    // ================================================================
    // RENDER MATRIX
    // ================================================================
    render_matrix_rows(occurrences) {
        let me = this;
        let tbody = $('#matrix-body');
        tbody.empty();

        let dated = occurrences.filter(function(o) { return !o.is_floating; });
        let floating = occurrences.filter(function(o) { return !!o.is_floating; });

        let seen_times = {};
        dated.forEach(function(o) {
            seen_times[o.scheduled_time] = o;
        });

        let time_rows = Object.values(seen_times).sort(function(a, b) {
            return me.time_sort_key(a) - me.time_sort_key(b);
        });

        if (!time_rows.length && !floating.length) {
            tbody.append(`
                <tr>
                    <td colspan="9" style="padding: 30px; text-align: center; color: #94a3b8;">
                        No tasks scheduled for ${me.filter_shift || 'this shift'} in this week.
                    </td>
                </tr>
            `);
            return;
        }

        // Dated Tasks
        time_rows.forEach(function(row_ref) {
            let time_str = row_ref.scheduled_time;
            let row_html = `
                <tr>
                    <td class="td-time">${me.format_time_label(time_str)}</td>
            `;

            for (let i = 0; i < 7; i++) {
                let cell_tasks = dated.filter(function(t) {
                    return t.scheduled_time === time_str && t.weekday_index === i;
                });

                row_html += `<td>`;
                cell_tasks.forEach(function(t) {
                    row_html += me.render_task_card(t);
                });
                row_html += `</td>`;
            }

            row_html += `<td class="td-floating"></td></tr>`;
            tbody.append(row_html);
        });

        // Floating Tasks
        if (floating.length) {
            let row_html = `
                <tr>
                    <td class="td-time">Anytime</td>
            `;

            for (let i = 0; i < 7; i++) {
                row_html += `<td></td>`;
            }

            row_html += `<td class="td-floating">`;
            floating.forEach(function(t) {
                row_html += me.render_task_card(t);
            });
            row_html += `</td></tr>`;

            tbody.append(row_html);
        }

        // Bind Card Selection
        $('.task-card-box').on('click', function() {
            $('.task-card-box').css('box-shadow', 'none').css('border-color', 'rgba(186, 230, 253, 0.9)');
            $(this).css('box-shadow', '0 0 0 2px #0f2744');

            let task_id = $(this).attr('data-id');
            let occurrence_date = $(this).attr('data-occurrence-date');

            me.selected_task_id = task_id;
            me.selected_occurrence_date = occurrence_date || moment().format('YYYY-MM-DD');

            me.load_inspector_details(task_id);
        });
    }

    // ================================================================
    // TASK CARD
    // ================================================================
    render_task_card(task) {
        let is_critical = task.clinical_priority === 'Critical';
        let badge_markup = task.clinical_priority 
            ? `<span class="task-badge ${is_critical ? 'task-badge-critical' : 'task-badge-warning'}">${task.clinical_priority}</span>`
            : '';

        let card_class = task.is_floating ? 'task-card-floating' : 'task-card-standard';

        return `
            <div class="task-card-box ${card_class}"
                 data-id="${task.name}"
                 data-occurrence-date="${task.occurrence_date || ''}">
                <div class="task-card-title">
                    [${task.participant || ''}] ${badge_markup}
                </div>
                <div class="task-card-name">
                    ${task.task_name || ''}
                </div>
            </div>
        `;
    }

    // ================================================================
    // TASK INSPECTOR
    // ================================================================
    load_inspector_details(task_id) {
        $('#panel-left-details').html(`
            <div style="padding: 16px; text-align: center; color: #0f2744;">
                <i class="fa fa-spinner fa-spin fa-2x"></i>
                <div style="margin-top: 8px; font-size: 12px;">Loading task context...</div>
            </div>
        `);

        frappe.call({
            method: 'care_management.care_management.page.support_task_schedule.support_task_schedule.get_staff_task_context',
            args: { task_id: task_id },
            callback: function(r) {
                if (r.exc) {
                    $('#panel-left-details').html(`
                        <div class="text-danger" style="padding: 12px;">
                            Unable to load task context.
                        </div>
                    `);
                    return;
                }

                const context = r.message || {};
                const task = context.task || {};
                const participant = context.participant || {};
                const assigned_staff = context.assigned_staff || [];
                const safe = (text) => frappe.utils.escape_html(text || '');

                // 1. Source Plan Context
                let plans_html = '';
                const source = context.source || {};
                if (source.doctype && source.name) {
                    plans_html += `
                        <button class="btn btn-sm btn-default staff-plan-view-btn"
                                data-doctype="${safe(source.doctype)}"
                                data-name="${safe(source.name)}"
                                style="width:100%; text-align:left; margin-bottom:6px; background:#ffffff; border:1px solid #cbd5e1; border-radius:6px;">
                            <i class="fa fa-file-text-o" style="color:#0f2744;"></i>
                            ${safe(source.label || source.doctype)}
                            <span style="float:right; color:#64748b; font-size:11px;">View</span>
                        </button>
                    `;
                }

                if (!plans_html) {
                    plans_html = `
                        <div style="padding:10px; border:1px dashed #cbd5e1; border-radius:6px; color:#64748b; font-size:11.5px;">
                            No linked care plan is available.
                        </div>
                    `;
                }

                // 2. Hospital Support Plan
                let hospital_html = '';
                const hospital = context.hospital_support_plan;
                if (hospital) {
                    hospital_html = `
                        <div style="background: rgba(254, 252, 232, 0.85); border: 1px solid #fef08a; border-radius: 8px; padding: 12px; margin-top: 14px; font-size: 12px;">
                            <div style="color: #854d0e; margin-bottom: 8px; font-weight: 700;">
                                <i class="fa fa-hospital-o"></i> Hospital Support Context
                            </div>
                            ${hospital.diagnosis ? `<p style="margin-bottom: 4px;"><strong>Diagnosis:</strong> ${safe(hospital.diagnosis)}</p>` : ''}
                            ${hospital.how_person_communicates ? `<p style="margin-bottom: 4px;"><strong>Communication:</strong> ${safe(hospital.how_person_communicates)}</p>` : ''}
                            ${hospital.mealtime_assistance_description ? `<p style="margin-bottom: 4px;"><strong>Mealtime Assistance:</strong> ${safe(hospital.mealtime_assistance_description)}</p>` : ''}
                            ${hospital.meals_texture ? `<p style="margin-bottom: 4px;"><strong>Meals Texture:</strong> ${safe(hospital.meals_texture)}</p>` : ''}
                            ${hospital.drinks_texture ? `<p style="margin-bottom: 4px;"><strong>Drinks Texture:</strong> ${safe(hospital.drinks_texture)}</p>` : ''}
                            ${hospital.personal_care_assistance_description ? `<p style="margin-bottom: 4px;"><strong>Personal Care:</strong> ${safe(hospital.personal_care_assistance_description)}</p>` : ''}
                            ${hospital.toileting_assistance_description ? `<p style="margin-bottom: 4px;"><strong>Toileting:</strong> ${safe(hospital.toileting_assistance_description)}</p>` : ''}
                            ${hospital.assistance_move_around_ward_description ? `<p style="margin-bottom: 4px;"><strong>Mobility:</strong> ${safe(hospital.assistance_move_around_ward_description)}</p>` : ''}
                        </div>
                    `;
                }

                // 3. Critical Care Plans
                const care_context = context.care_context || {};
                let critical_care_html = '';
                const care_links = [];
                if (care_context.hospital_support_plan) care_links.push({ doctype: 'Hospital Support Plan', name: care_context.hospital_support_plan, label: 'Hospital Support Plan' });
                if (care_context.falls_risk_plan) care_links.push({ doctype: 'Falls Risk Plan', name: care_context.falls_risk_plan, label: 'Falls Risk Plan' });
                if (care_context.epilepsy_management_plan) care_links.push({ doctype: 'Epilepsy Management Plan', name: care_context.epilepsy_management_plan, label: 'Epilepsy Management Plan' });

                if (care_links.length) {
                    critical_care_html = `
                        <div style="margin-top:14px; padding:12px; border:1px solid #e2e8f0; border-radius:8px; background:rgba(255,255,255,0.7);">
                            <div style="font-weight:700; margin-bottom:8px; color:#0f2744; font-size:11.5px; text-transform:uppercase; letter-spacing:0.03em;">
                                Critical Care Plans
                            </div>
                            ${care_links.map(function(plan) {
                                return `
                                    <button class="btn btn-sm btn-default critical-care-plan-btn"
                                            data-doctype="${safe(plan.doctype)}"
                                            data-name="${safe(plan.name)}"
                                            style="width:100%; text-align:left; margin-bottom:4px; background:#ffffff; border:1px solid #cbd5e1; border-radius:6px;">
                                        <i class="fa fa-medkit" style="color:#0f2744;"></i> ${safe(plan.label)}
                                        <span style="float:right; color:#64748b; font-size:11px;">View</span>
                                    </button>
                                `;
                            }).join('')}
                        </div>
                    `;
                }

                // 4. Assigned Staff
                let assigned_html = '';
                if (assigned_staff.length) {
                    assigned_staff.forEach(function(row) {
                        assigned_html += `
                            <div style="font-size: 12px; margin-bottom: 4px; color:#334155;">
                                <strong>${safe(row.staff_user || '')}</strong>
                                ${row.role ? ` — <span style="color:#64748b;">${safe(row.role)}</span>` : ''}
                            </div>
                        `;
                    });
                } else {
                    assigned_html = `<span style="color:#64748b; font-size:12px;">No specific staff assignment recorded.</span>`;
                }

                // 5. Assemble Left Panel
                const html = `
                    <div>
                        <div class="details-subheading">Task Overview</div>
                        <p style="margin-bottom:6px;"><strong>Task:</strong> ${safe(task.task_name || '')}</p>
                        <p style="margin-bottom:6px;"><strong>Participant:</strong> ${safe(participant.name || '')}</p>
                        <p style="margin-bottom:6px;"><strong>Priority:</strong> ${safe(task.clinical_priority || 'Normal')}</p>
                        <p style="margin-bottom:6px;"><strong>Category:</strong> ${safe(task.task_category || '-')}</p>
                        <p style="margin-bottom:10px;"><strong>Instructions:</strong> ${safe(task.description || 'None')}</p>

                        <div class="details-subheading">Care Plan / Source</div>
                        <div>${plans_html}</div>
                        ${hospital_html}
                        ${critical_care_html}

                        <div class="details-subheading">Assigned Staff</div>
                        ${assigned_html}
                    </div>
                `;

                $('#panel-left-details').html(html);
            }
        });
    }

    // ================================================================
    // RECORD DELIVERY
    // ================================================================
    show_outcome_dialog() {
        if (!this.selected_task_id) {
            frappe.msgprint('Please select a support task card first.');
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
                    method: 'care_management.care_management.page.support_task_schedule.support_task_schedule.record_task_outcome',
                    args: {
                        task_id: me.selected_task_id,
                        scheduled_date: me.selected_occurrence_date,
                        outcome: values.outcome,
                        execution_notes: values.execution_notes,
                        exception_type: values.exception_type,
                        follow_up_required: values.follow_up_required ? 1 : 0
                    },
                    callback: function(r) {
                        if (!r.message) return;
                        frappe.show_alert({
                            message: `Task recorded as ${r.message.outcome}.`,
                            indicator: 'green'
                        });
                        d.hide();
                        me.load_schedule_grid();
                        me.load_inspector_details(me.selected_task_id);
                    }
                });
            }
        });
        d.show();
    }

    // ================================================================
    // START TASK
    // ================================================================
    start_task_execution() {
        if (!this.selected_task_id) {
            frappe.msgprint('Please select a support task card first.');
            return;
        }

        let me = this;
        frappe.call({
            method: 'care_management.care_management.page.support_task_schedule.support_task_schedule.start_task_execution',
            args: {
                task_id: me.selected_task_id,
                scheduled_date: me.selected_occurrence_date
            },
            callback: function(r) {
                if (!r.message) return;
                if (r.message.status === 'already_completed') {
                    frappe.msgprint(`This task has already been completed with outcome: <b>${r.message.outcome}</b>`);
                    return;
                }
                frappe.show_alert({ message: 'Task started.', indicator: 'green' });
                me.load_schedule_grid();
                me.load_inspector_details(me.selected_task_id);
            }
        });
    }

    // ================================================================
    // LOG MISSED TASK
    // ================================================================
    show_missed_dialog() {
        if (!this.selected_task_id) {
            frappe.msgprint('Please select a support task card from the matrix grid first.');
            return;
        }

        let me = this;
        let d = new frappe.ui.Dialog({
            title: 'Log Task as Missed / Omission',
            fields: [
                {
                    label: 'Omission Reason Category',
                    fieldname: 'reason_category',
                    fieldtype: 'Select',
                    options: '\nParticipant Refused\nParticipant Hospitalized / Absent\nStock / Medication Unavailable\nClinical Risk / Adverse Reaction\nStaff Shortage\nOther',
                    reqd: 1
                },
                {
                    label: 'Omission Clinical Justification',
                    fieldname: 'omission_notes',
                    fieldtype: 'Small Text',
                    reqd: 1
                },
                {
                    label: 'Escalate as Incident Report',
                    fieldname: 'incident_escalated',
                    fieldtype: 'Check'
                }
            ],
            primary_action_label: 'Submit Omission',
            primary_action: function(values) {
                frappe.call({
                    method: 'care_management.care_management.page.support_task_schedule.support_task_schedule.record_task_outcome',
                    args: {
                        task_id: me.selected_task_id,
                        scheduled_date: me.selected_occurrence_date,
                        outcome: 'Missed',
                        execution_notes: values.omission_notes,
                        exception_type: values.reason_category,
                        follow_up_required: 0
                    },
                    callback: function(r) {
                        if (!r.message) return;
                        frappe.show_alert({ message: 'Task omission recorded.', indicator: 'orange' });
                        d.hide();
                        me.load_schedule_grid();
                        me.load_inspector_details(me.selected_task_id);
                    }
                });
            }
        });
        d.show();
    }
}