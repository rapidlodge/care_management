frappe.pages['manager-dashboard'].on_page_load = function(wrapper) {
    let page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Manager Dashboard',
        single_column: true
    });

    wrapper.manager_dashboard = new ManagerDashboard(page);
};

class ManagerDashboard {
    constructor(page) {
        this.page = page;
        this.start_date = moment().startOf('day').format('YYYY-MM-DD');
        this.end_date = moment().endOf('day').format('YYYY-MM-DD');
        this.status = '';
        this.participant = '';
        this.attention_type = 'all';

        this.make_layout();
        this.load_dashboard();
    }

    // ================================================================
    // PAGE LAYOUT
    // ================================================================
    make_layout() {
        let me = this;

        this.page.set_primary_action('Refresh', function() {
            me.load_dashboard();
        });

        let html = `
            <style>
                .manager-dashboard {
                    padding: 16px 14px 40px 14px;
                    background: radial-gradient(circle at 10% 10%, rgba(241, 245, 249, 0.8) 0%, rgba(248, 250, 252, 0.6) 100%);
                    font-family: inherit;
                    color: #0f172a;
                }

                .dashboard-header {
                    margin-bottom: 20px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }

                .dashboard-title {
                    font-size: 22px;
                    font-weight: 800;
                    letter-spacing: -0.02em;
                    color: #0f2744;
                }

                .dashboard-subtitle {
                    color: #64748b;
                    font-size: 13px;
                    margin-top: 2px;
                }

                /* GLASSMORPHIC FILTER PANEL */
                .manager-filter-bar {
                    background: rgba(255, 255, 255, 0.82);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    border: 1px solid rgba(203, 213, 225, 0.8);
                    box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.04), 0 4px 6px -2px rgba(15, 23, 42, 0.02);
                    border-radius: 14px;
                    padding: 16px 18px;
                    margin-bottom: 24px;
                    position: relative;
                    z-index: 1001; /* Fix for dropdown overlapping lower cards */
                }

                .manager-filter-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                    gap: 14px;
                    align-items: end;
                }

                .manager-filter-item {
                    display: flex;
                    flex-direction: column;
                    justify-content: flex-end;
                }

                .manager-filter-label {
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

                /* Normalize all filter control heights & Frappe Link wrapper styling */
                .manager-filter-bar .form-control,
                .manager-filter-bar input[type="date"],
                .manager-filter-bar select {
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

                #manager-dashboard-participant-wrapper .frappe-control {
                    margin-bottom: 0px !important;
                }
                #manager-dashboard-participant-wrapper .form-group {
                    margin-bottom: 0px !important;
                }
                #manager-dashboard-participant-wrapper .control-label {
                    display: none !important;
                }

                /* Fix link dropdown z-index position */
                .manager-filter-bar .awesomplete {
                    position: relative;
                    z-index: 1005;
                }
                .manager-filter-bar .awesomplete > ul {
                    z-index: 1005 !important;
                    border-radius: 8px !important;
                    box-shadow: 0 10px 25px rgba(15, 23, 42, 0.15) !important;
                    border: 1px solid #cbd5e1 !important;
                }

                .manager-filter-actions {
                    display: flex;
                    gap: 8px;
                    height: 34px;
                    align-items: center;
                }

                /* NAVY BLUE ACTION BUTTONS */
                .btn-navy-primary {
                    background: linear-gradient(135deg, #0f2744 0%, #1e3a5f 100%);
                    color: #ffffff !important;
                    border: none;
                    border-radius: 8px;
                    font-weight: 600;
                    height: 34px;
                    padding: 0 14px;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    gap: 6px;
                    transition: all 0.2s ease;
                    box-shadow: 0 4px 12px rgba(15, 39, 68, 0.2);
                }

                .btn-navy-primary:hover {
                    background: linear-gradient(135deg, #0a1b30 0%, #142a45 100%);
                    transform: translateY(-1px);
                    box-shadow: 0 6px 16px rgba(15, 39, 68, 0.3);
                }

                .btn-glass-reset {
                    background: rgba(255, 255, 255, 0.9);
                    border: 1px solid #cbd5e1;
                    border-radius: 8px;
                    color: #475569;
                    height: 34px;
                    width: 36px;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    transition: all 0.2s;
                }

                .btn-glass-reset:hover {
                    background: #f1f5f9;
                    color: #0f2744;
                }

                .manager-active-filters {
                    margin-top: 14px;
                    padding-top: 10px;
                    border-top: 1px dashed rgba(203, 213, 225, 0.8);
                    font-size: 12px;
                    color: #64748b;
                }

                .manager-active-filters strong {
                    color: #0f2744;
                }

                /* KPI CARDS */
                .manager-kpi-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                    gap: 14px;
                    margin-bottom: 24px;
                    position: relative;
                    z-index: 1;
                }

                .manager-kpi-card {
                    background: rgba(255, 255, 255, 0.78);
                    backdrop-filter: blur(10px);
                    -webkit-backdrop-filter: blur(10px);
                    border: 1px solid rgba(226, 232, 240, 0.9);
                    border-radius: 14px;
                    padding: 16px;
                    position: relative;
                    overflow: hidden;
                    box-shadow: 0 4px 15px rgba(15, 23, 42, 0.03);
                    transition: all 0.2s ease;
                }

                .manager-kpi-card:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
                }

                .manager-kpi-card::before {
                    content: "";
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    height: 3.5px;
                }

                .manager-kpi-card.kpi-total::before { background: linear-gradient(90deg, #1e3a5f, #3b82f6); }
                .manager-kpi-card.kpi-completed::before { background: linear-gradient(90deg, #059669, #34d399); }
                .manager-kpi-card.kpi-missed::before { background: linear-gradient(90deg, #dc2626, #f87171); }
                .manager-kpi-card.kpi-exceptions::before { background: linear-gradient(90deg, #d97706, #fbbf24); }
                .manager-kpi-card.kpi-followup::before { background: linear-gradient(90deg, #0284c7, #38bdf8); }
                .manager-kpi-card.kpi-progress::before { background: linear-gradient(90deg, #6366f1, #a5b4fc); }

                .manager-kpi-label {
                    font-size: 11px;
                    font-weight: 700;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                    color: #64748b;
                }

                .manager-kpi-value {
                    font-size: 26px;
                    font-weight: 800;
                    color: #0f2744;
                    margin-top: 6px;
                    letter-spacing: -0.02em;
                }

                /* GLASS SECTIONS */
                .manager-section {
                    background: rgba(255, 255, 255, 0.75);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    border: 1px solid rgba(226, 232, 240, 0.8);
                    border-radius: 14px;
                    margin-bottom: 24px;
                    overflow: hidden;
                    box-shadow: 0 6px 20px rgba(15, 23, 42, 0.03);
                    position: relative;
                    z-index: 1;
                }

                .manager-section-header {
                    padding: 14px 18px;
                    background: rgba(248, 250, 252, 0.7);
                    border-bottom: 1px solid rgba(226, 232, 240, 0.8);
                    font-size: 13.5px;
                    font-weight: 700;
                    color: #0f2744;
                }

                .manager-section-body {
                    padding: 16px;
                }

                /* ATTENTION PILLS */
                .manager-attention-filter {
                    background: rgba(255, 255, 255, 0.9);
                    border: 1px solid #cbd5e1;
                    color: #475569;
                    font-weight: 600;
                    border-radius: 20px;
                    padding: 4px 14px;
                    font-size: 11px;
                    transition: all 0.2s;
                }

                .manager-attention-filter:hover {
                    background: #f1f5f9;
                    color: #0f2744;
                }

                .manager-attention-filter.active {
                    background: #0f2744;
                    border-color: #0f2744;
                    color: #ffffff;
                    box-shadow: 0 3px 8px rgba(15, 39, 68, 0.25);
                }

                /* CARDS */
                .manager-cards-grid {
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: 14px;
                    align-items: start;
                }

                .manager-review-card {
                    border-radius: 12px;
                    padding: 15px;
                    border: 1px solid rgba(226, 232, 240, 0.9);
                    backdrop-filter: blur(8px);
                    -webkit-backdrop-filter: blur(8px);
                    cursor: pointer;
                    transition: all 0.2s ease;
                    min-width: 0;
                    overflow: hidden;
                    word-break: break-word;
                    overflow-wrap: anywhere;
                }

                .manager-review-card:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 8px 18px rgba(15, 23, 42, 0.05);
                }

                .manager-review-title {
                    font-weight: 700;
                    font-size: 13.5px;
                    color: #0f2744;
                }

                .manager-review-meta {
                    color: #64748b;
                    font-size: 11.5px;
                    margin-top: 3px;
                }

                .manager-review-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
                    gap: 6px 12px;
                    margin-top: 10px;
                    font-size: 11.5px;
                    color: #475569;
                    padding-top: 10px;
                    border-top: 1px solid rgba(0,0,0,0.04);
                }

                .manager-review-grid strong {
                    color: #0f2744;
                }

                /* LIGHT COLORFUL TONES */
                .card-tone-success {
                    background: rgba(236, 253, 245, 0.75);
                    border-color: rgba(167, 243, 208, 0.8) !important;
                }

                .card-tone-warning {
                    background: rgba(254, 252, 232, 0.8);
                    border-color: rgba(253, 230, 138, 0.8) !important;
                }

                .card-tone-danger {
                    background: rgba(254, 242, 242, 0.75);
                    border-color: rgba(254, 202, 202, 0.8) !important;
                }

                .card-tone-info {
                    background: rgba(240, 249, 255, 0.75);
                    border-color: rgba(186, 230, 253, 0.8) !important;
                }

                .card-tone-neutral {
                    background: rgba(255, 255, 255, 0.8);
                    border-color: rgba(226, 232, 240, 0.8) !important;
                }

                /* BADGES */
                .manager-badge {
                    display: inline-flex;
                    align-items: center;
                    padding: 3px 8px;
                    border-radius: 6px;
                    font-size: 10px;
                    font-weight: 700;
                }

                .badge-high { background: #fee2e2; color: #991b1b; }
                .badge-med { background: #fef3c7; color: #92400e; }
                .badge-low { background: #f1f5f9; color: #475569; }

                .manager-empty-state, .manager-loading {
                    padding: 40px 20px;
                    text-align: center;
                    color: #94a3b8;
                    font-size: 13px;
                    grid-column: 1 / -1;
                }

                @media (max-width: 900px) {
                    .manager-cards-grid { grid-template-columns: 1fr; }
                }
                @media (max-width: 768px) {
                    .manager-filter-grid { grid-template-columns: 1fr; }
                    .manager-kpi-grid { grid-template-columns: repeat(2, 1fr); }
                }
            </style>

            <div class="manager-dashboard">
                <div class="dashboard-header">
                    <div>
                        <div class="dashboard-title">Manager Dashboard</div>
                        <div class="dashboard-subtitle">Operational oversight, execution review and follow-up management.</div>
                    </div>
                </div>

                <!-- FILTERS -->
                <div class="manager-filter-bar">
                    <div class="manager-filter-grid">
                        <div class="manager-filter-item">
                            <label class="manager-filter-label">Start Date</label>
                            <input type="date" id="manager-dashboard-start-date" class="form-control">
                        </div>
                        <div class="manager-filter-item">
                            <label class="manager-filter-label">End Date</label>
                            <input type="date" id="manager-dashboard-end-date" class="form-control">
                        </div>
                        <div class="manager-filter-item">
                            <label class="manager-filter-label">Participant</label>
                            <div id="manager-dashboard-participant-wrapper"></div>
                        </div>
                        <div class="manager-filter-item">
                            <label class="manager-filter-label">Status</label>
                            <select id="manager-dashboard-status" class="form-control">
                                <option value="">All</option>
                                <option value="In Progress">In Progress</option>
                                <option value="Completed">Completed</option>
                                <option value="Delivered">Delivered</option>
                                <option value="Partially Completed">Partially Completed</option>
                                <option value="Refused / Declined">Refused / Declined</option>
                                <option value="Not Applicable">Not Applicable</option>
                                <option value="Missed">Missed</option>
                                <option value="Cancelled">Cancelled</option>
                            </select>
                        </div>
                        <div class="manager-filter-actions">
                            <button class="btn btn-navy-primary" id="manager-dashboard-apply" style="flex: 1;">
                                <i class="fa fa-filter"></i> Apply
                            </button>
                            <button class="btn btn-glass-reset" id="manager-dashboard-reset" title="Reset filters">
                                <i class="fa fa-refresh"></i>
                            </button>
                        </div>
                    </div>
                    <div id="manager-active-filters" class="manager-active-filters"></div>
                </div>

                <!-- KPI AREA -->
                <div id="manager-dashboard-kpis" class="manager-kpi-grid"></div>

                <!-- NEEDS ATTENTION -->
                <div class="manager-section">
                    <div class="manager-section-header" style="display: flex; justify-content: space-between; align-items: center;">
                        <span>Needs Attention</span>
                        <span id="manager-attention-count" class="text-muted" style="font-size: 11px; font-weight: normal;">0 items</span>
                    </div>
                    <div class="manager-section-body">
                        <div style="display: flex; gap: 6px; margin-bottom: 16px; flex-wrap: wrap;">
                            <button type="button" class="btn btn-xs manager-attention-filter active" data-attention-type="all">All</button>
                            <button type="button" class="btn btn-xs manager-attention-filter" data-attention-type="follow_up">Follow-up</button>
                            <button type="button" class="btn btn-xs manager-attention-filter" data-attention-type="missed">Missed</button>
                            <button type="button" class="btn btn-xs manager-attention-filter" data-attention-type="exception">Exceptions</button>
                        </div>
                        <div id="manager-attention-results" class="manager-cards-grid">
                            <div class="manager-loading">Loading...</div>
                        </div>
                    </div>
                </div>

                <!-- MANAGER REVIEW -->
                <div class="manager-section">
                    <div class="manager-section-header">Manager Review</div>
                    <div id="manager-dashboard-results" class="manager-section-body manager-cards-grid"></div>
                </div>

                <!-- OPEN FOLLOW-UPS -->
                <div class="manager-section">
                    <div class="manager-section-header" style="display: flex; justify-content: space-between; align-items: center;">
                        <span>Open Follow-ups</span>
                        <span id="manager-follow-up-count" class="text-muted" style="font-size: 11px; font-weight: normal;">0 items</span>
                    </div>
                    <div id="manager-follow-up-results" class="manager-section-body manager-cards-grid">
                        <div class="manager-loading">Loading...</div>
                    </div>
                </div>
            </div>
        `;

        $(this.page.body).html(html);

        this.bind_attention_filters();
        this.load_attention_items();

        $('#manager-dashboard-start-date').val(this.start_date);
        $('#manager-dashboard-end-date').val(this.end_date);
        $('#manager-dashboard-status').val(this.status);

        // Standard Link field control for participant
        this.participant_control = frappe.ui.form.make_control({
            df: {
                fieldtype: 'Link',
                fieldname: 'manager_dashboard_participant',
                options: 'Participant Profile',
                placeholder: 'All Participants'
            },
            parent: $('#manager-dashboard-participant-wrapper').get(0),
            render_input: true
        });
        this.participant_control.refresh();

        if (this.participant) {
            this.participant_control.set_value(this.participant);
        }

        $('#manager-dashboard-apply').on('click', function() {
            me.apply_filters();
        });

        $('#manager-dashboard-reset').on('click', function() {
            me.reset_filters();
        });

        this.render_active_filters();
    }

    // ================================================================
    // BIND ATTENTION FILTERS
    // ================================================================
    bind_attention_filters() {
        let me = this;
        $(this.page.body).off('click.manager_attention', '.manager-attention-filter');
        $(this.page.body).on('click.manager_attention', '.manager-attention-filter', function() {
            let attention_type = $(this).attr('data-attention-type') || 'all';
            me.attention_type = attention_type;
            $(me.page.body).find('.manager-attention-filter').removeClass('active');
            $(this).addClass('active');
            me.load_attention_items();
        });
    }

    // ================================================================
    // APPLY FILTERS
    // ================================================================
    apply_filters() {
        let start_date = $('#manager-dashboard-start-date').val();
        let end_date = $('#manager-dashboard-end-date').val();
        let status = $('#manager-dashboard-status').val();

        if (!start_date || !end_date) {
            frappe.msgprint('Please select both Start Date and End Date.');
            return;
        }

        if (start_date > end_date) {
            frappe.msgprint('Start Date cannot be after End Date.');
            return;
        }

        this.start_date = start_date;
        this.end_date = end_date;
        this.status = status || '';
        this.participant = this.get_participant();

        this.render_active_filters();
        this.load_dashboard();
    }

    // ================================================================
    // RESET FILTERS
    // ================================================================
    reset_filters() {
        this.start_date = moment().startOf('day').format('YYYY-MM-DD');
        this.end_date = moment().endOf('day').format('YYYY-MM-DD');
        this.status = '';
        this.participant = '';
        this.attention_type = 'all';

        $('#manager-dashboard-start-date').val(this.start_date);
        $('#manager-dashboard-end-date').val(this.end_date);
        $('#manager-dashboard-status').val('');

        if (this.participant_control) {
            this.participant_control.set_value('');
        }

        $(this.page.body).find('.manager-attention-filter').removeClass('active');
        $(this.page.body).find('.manager-attention-filter[data-attention-type="all"]').addClass('active');

        this.render_active_filters();
        this.load_dashboard();
    }

    // ================================================================
    // GET PARTICIPANT
    // ================================================================
    get_participant() {
        if (this.participant_control) {
            return this.participant_control.get_value() || '';
        }
        return this.participant || '';
    }

    // ================================================================
    // RENDER ACTIVE FILTERS
    // ================================================================
    render_active_filters() {
        let me = this;
        let parts = [];
        parts.push(`Date: ${me.start_date} to ${me.end_date}`);

        if (me.status) {
            parts.push(`Status: ${me.status}`);
        }

        let participant_value = me.get_participant();
        if (participant_value) {
            parts.push(`Participant: ${participant_value}`);
        } else {
            parts.push('Participant: All Participants');
        }

        $('#manager-active-filters').html(
            '<strong>Showing:</strong> ' + frappe.utils.escape_html(parts.join('  ·  '))
        );
    }

    get_start_date() {
        return $('#manager-dashboard-start-date').val() || this.start_date;
    }

    get_end_date() {
        return $('#manager-dashboard-end-date').val() || this.end_date;
    }

    // ================================================================
    // LOAD DASHBOARD
    // ================================================================
    load_dashboard() {
        let me = this;

        $('#manager-dashboard-results').html(`
            <div class="manager-loading">
                <i class="fa fa-spinner fa-spin fa-2x" style="color:#0f2744;"></i>
                <div style="margin-top:8px;">Loading manager review...</div>
            </div>
        `);

        $('#manager-dashboard-kpis').html('');

        frappe.call({
            method: 'care_management.care_management.page.manager_dashboard.manager_dashboard.get_manager_dashboard_data',
            args: {
                start_date: this.start_date,
                end_date: this.end_date,
                status: this.status || null,
                participant: this.get_participant() || null
            },
            callback: function(r) {
                if (r.exc) {
                    $('#manager-dashboard-results').html(`
                        <div class="text-danger manager-empty-state">
                            Unable to load Manager Dashboard.
                        </div>
                    `);
                    return;
                }

                let data = r.message || {};
                let kpis = data.kpis || {};
                if (data.follow_up_count != null) {
                    kpis.follow_up = data.follow_up_count;
                }

                me.render_kpis(kpis);
                me.load_attention_items();
                me.render_reviews(data.reviews || []);
                me.load_follow_ups();
            }
        });
    }

    // ================================================================
    // LOAD ATTENTION ITEMS
    // ================================================================
    load_attention_items() {
        let me = this;

        $('#manager-attention-results').html(`
            <div class="manager-loading">
                <i class="fa fa-spinner fa-spin"></i> Loading...
            </div>
        `);

        frappe.call({
            method: 'care_management.care_management.page.manager_dashboard.manager_dashboard.get_manager_attention_items',
            args: {
                start_date: me.get_start_date(),
                end_date: me.get_end_date(),
                attention_type: me.attention_type || 'all',
                limit: 50,
                participant: me.get_participant() || null
            },
            callback: function(r) {
                if (r.exc) {
                    $('#manager-attention-results').html(`
                        <div class="text-danger manager-empty-state">
                            Unable to load attention items.
                        </div>
                    `);
                    return;
                }

                let items = r.message || [];
                me.render_attention_items(items);
            },
            error: function() {
                $('#manager-attention-results').html(`
                    <div class="text-danger manager-empty-state">
                        Unable to load attention items.
                    </div>
                `);
            }
        });
    }

    // ================================================================
    // LOAD FOLLOW-UPS
    // ================================================================
    load_follow_ups() {
        let me = this;

        $('#manager-follow-up-results').html(`
            <div class="manager-loading">
                <i class="fa fa-spinner fa-spin"></i> Loading follow-ups...
            </div>
        `);

        frappe.call({
            method: 'care_management.care_management.page.manager_dashboard.manager_dashboard.get_manager_follow_ups',
            args: {
                status: '',
                start_date: me.get_start_date(),
                end_date: me.get_end_date(),
                limit: 50,
                participant: me.get_participant() || null
            },
            callback: function(r) {
                if (r.exc) {
                    $('#manager-follow-up-results').html(`
                        <div class="text-danger manager-empty-state">
                            Unable to load follow-ups.
                        </div>
                    `);
                    return;
                }

                me.render_follow_ups(r.message || []);
            },
            error: function() {
                $('#manager-follow-up-results').html(`
                    <div class="text-danger manager-empty-state">
                        Unable to load follow-ups.
                    </div>
                `);
            }
        });
    }

    // ================================================================
    // RENDER FOLLOW-UPS
    // ================================================================
    render_follow_ups(follow_ups) {
        let me = this;
        follow_ups = follow_ups || [];

        $('#manager-follow-up-count').text(`${follow_ups.length} item${follow_ups.length === 1 ? '' : 's'}`);

        if (!follow_ups.length) {
            $('#manager-follow-up-results').html(`
                <div class="manager-empty-state">
                    <i class="fa fa-check-circle" style="font-size: 24px; color: #10b981; margin-bottom: 8px;"></i>
                    <div>No open follow-ups.</div>
                </div>
            `);
            return;
        }

        let html = '';
        follow_ups.forEach(function(row) {
            let priority = me.safe(row.priority);
            let status = me.safe(row.status);
            let participant = me.safe(row.participant || 'Participant not set');
            let task = me.safe(row.support_task || 'Support Task');
            let assigned = me.safe(row.assigned_to);
            let due_date = me.safe(row.due_date);
            let reason = me.safe(row.follow_up_reason);

            let priority_badge = priority === 'High' || priority === 'Critical'
                ? 'badge-high'
                : priority === 'Medium' ? 'badge-med' : 'badge-low';

            html += `
                <div class="manager-review-card ${me.follow_up_tone_class(row)}" data-follow-up-name="${me.safe(row.name)}">
                    <div style="display:flex; justify-content:space-between; gap:10px; align-items: flex-start;">
                        <div>
                            <div class="manager-review-title">${task}</div>
                            <div class="manager-review-meta"><i class="fa fa-user-circle" style="margin-right:4px;"></i>${participant}</div>
                        </div>
                        <span class="manager-badge ${priority_badge}">${priority}</span>
                    </div>

                    <div class="manager-review-grid">
                        <div><strong>Follow-up:</strong> ${me.safe(row.name)}</div>
                        <div><strong>Reason:</strong> ${reason}</div>
                        <div><strong>Assigned:</strong> ${assigned}</div>
                        <div><strong>Due:</strong> ${due_date}</div>
                        <div><strong>Status:</strong> ${status}</div>
                    </div>
                </div>
            `;
        });

        $('#manager-follow-up-results').html(html);
    }

    // ================================================================
    // RENDER KPI
    // ================================================================
    render_kpis(kpis) {
        let cards = [
            { label: 'Total', value: kpis.total || 0, class: 'kpi-total' },
            { label: 'Completed', value: kpis.completed || 0, class: 'kpi-completed' },
            { label: 'Missed', value: kpis.missed || 0, class: 'kpi-missed' },
            { label: 'Exceptions', value: kpis.exceptions || 0, class: 'kpi-exceptions' },
            { label: 'Follow-up', value: kpis.follow_up_count != null ? kpis.follow_up_count : (kpis.follow_up || 0), class: 'kpi-followup' },
            { label: 'In Progress', value: kpis.in_progress || 0, class: 'kpi-progress' }
        ];

        let html = '';
        cards.forEach(function(card) {
            html += `
                <div class="manager-kpi-card ${card.class}">
                    <div class="manager-kpi-label">${frappe.utils.escape_html(card.label)}</div>
                    <div class="manager-kpi-value">${card.value}</div>
                </div>
            `;
        });

        $('#manager-dashboard-kpis').html(html);
    }

    // ================================================================
    // RENDER NEEDS ATTENTION
    // ================================================================
    render_attention_items(items) {
        let me = this;
        items = items || [];

        $('#manager-attention-count').text(`${items.length} item${items.length === 1 ? '' : 's'}`);

        if (!items.length) {
            $('#manager-attention-results').html(`
                <div class="manager-empty-state">
                    <i class="fa fa-check-circle" style="font-size: 24px; color: #10b981; margin-bottom: 8px;"></i>
                    <div>No items currently require manager attention.</div>
                </div>
            `);
            return;
        }

        let html = '';
        items.forEach(function(row) {
            let priority = row.review_priority || 'Low';
            let priority_badge = priority === 'High' ? 'badge-high' : priority === 'Medium' ? 'badge-med' : 'badge-low';
            let border_accent = priority === 'High' ? '#dc2626' : priority === 'Medium' ? '#d97706' : '#94a3b8';

            let task_name = me.safe(row.task_name || 'Support Task');
            let participant = me.safe(row.participant || 'Participant not set');
            let status = me.safe(row.status);
            let category = me.safe(row.review_category);
            let reason = me.safe(row.attention_reason);
            let date = me.safe(row.scheduled_date);
            let time = me.safe(row.scheduled_time);
            let execution_instance = me.safe(row.execution_instance);

            html += `
                <div class="manager-review-card ${me.review_tone_class(row)}" 
                     data-execution-instance="${execution_instance}"
                     style="border-left: 4px solid ${border_accent};">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px;">
                        <div>
                            <div class="manager-review-title">${task_name}</div>
                            <div class="manager-review-meta"><i class="fa fa-user-circle" style="margin-right:4px;"></i>${participant}</div>
                        </div>
                        <span class="manager-badge ${priority_badge}">${me.safe(priority)}</span>
                    </div>

                    <div style="margin-top: 8px; font-size: 12px; color: #334155;">
                        <strong style="color: #0f2744;">Attention:</strong> ${reason}
                    </div>

                    <div class="manager-review-grid">
                        <div><strong>Status:</strong> ${status}</div>
                        <div><strong>Category:</strong> ${category}</div>
                        <div><strong>Date:</strong> ${date}</div>
                        <div><strong>Time:</strong> ${time}</div>
                    </div>
                </div>
            `;
        });

        $('#manager-attention-results').html(html);

        $('#manager-attention-results').find('.manager-review-card').on('click', function() {
            let execution_instance = $(this).attr('data-execution-instance');
            if (!execution_instance) return;
            me.open_execution_review(execution_instance);
        });
    }

    // ================================================================
    // OPEN EXECUTION REVIEW
    // ================================================================
    open_execution_review(execution_instance) {
        let me = this;
        let dialog = new frappe.ui.Dialog({
            title: 'Manager Execution Review',
            size: 'large',
            primary_action_label: 'Save Review',
            primary_action: function(values) {
                me.save_manager_review(execution_instance, values, dialog);
            },
            fields: [
                { fieldname: 'execution_instance', fieldtype: 'Data', label: 'Execution Instance', read_only: 1 },
                { fieldname: 'support_task', fieldtype: 'Data', label: 'Support Task', read_only: 1 },
                { fieldname: 'task_name', fieldtype: 'Data', label: 'Task', read_only: 1 },
                { fieldname: 'participant', fieldtype: 'Data', label: 'Participant', read_only: 1 },
                { fieldname: 'staff', fieldtype: 'Data', label: 'Assigned Staff', read_only: 1 },
                { fieldname: 'scheduled_date', fieldtype: 'Date', label: 'Scheduled Date', read_only: 1 },
                { fieldname: 'scheduled_time', fieldtype: 'Time', label: 'Scheduled Time', read_only: 1 },
                { fieldname: 'status', fieldtype: 'Data', label: 'Status', read_only: 1 },
                { fieldname: 'review_category', fieldtype: 'Data', label: 'Review Category', read_only: 1 },
                { fieldname: 'review_priority', fieldtype: 'Data', label: 'Review Priority', read_only: 1 },
                { fieldname: 'exception_type', fieldtype: 'Data', label: 'Exception', read_only: 1 },
                { fieldname: 'follow_up_required', fieldtype: 'Check', label: 'Follow-up Required', read_only: 1 },
                { fieldname: 'notes', fieldtype: 'Small Text', label: 'Notes', read_only: 1 },
                { fieldname: 'follow_up_section', fieldtype: 'Section Break', label: 'Follow-up' },
                {
                    fieldname: 'follow_up_action',
                    fieldtype: 'Select',
                    label: 'Manager Follow-up Action',
                    options: ['', 'Acknowledge', 'Create Follow-up', 'Mark No Follow-up Required'].join('\n'),
                    default: ''
                },
                { fieldname: 'follow_up_notes', fieldtype: 'Small Text', label: 'Manager Notes' }
            ]
        });

        dialog.show();

        dialog.set_df_property('execution_instance', 'description', 'Loading execution review...');

        frappe.call({
            method: 'care_management.care_management.page.manager_dashboard.manager_dashboard.get_execution_review_detail',
            args: { execution_instance: execution_instance },
            callback: function(r) {
                if (r.exc || !r.message) {
                    dialog.set_df_property('execution_instance', 'description', 'Unable to load execution review.');
                    frappe.msgprint('Unable to load execution review details.');
                    return;
                }

                const data = r.message;
                dialog.set_value('execution_instance', data.execution_instance || '');
                dialog.set_value('support_task', data.support_task || '');
                dialog.set_value('task_name', data.task_name || '');
                dialog.set_value('participant', data.participant || '');

                let staff_text = '';
                if (Array.isArray(data.assigned_staff) && data.assigned_staff.length) {
                    staff_text = data.assigned_staff.map(function(row) {
                        let value = row.staff_user || '';
                        if (row.role) value += ' — ' + row.role;
                        return value;
                    }).join(', ');
                } else {
                    staff_text = data.executed_by || '';
                }

                dialog.set_value('staff', staff_text);
                dialog.set_value('scheduled_date', data.scheduled_date || '');
                dialog.set_value('scheduled_time', data.scheduled_time || '');
                dialog.set_value('status', data.status || '');
                dialog.set_value('review_category', data.review_category || '');
                dialog.set_value('review_priority', data.review_priority || '');
                dialog.set_value('exception_type', data.exception_type || '');
                dialog.set_value('follow_up_required', data.follow_up_required ? 1 : 0);
                dialog.set_value('notes', data.execution_notes || '');
                dialog.set_df_property('execution_instance', 'description', '');
                dialog.refresh();
            }
        });
    }

    // ================================================================
    // SAVE MANAGER REVIEW
    // ================================================================
    save_manager_review(execution_instance, values, dialog) {
        let me = this;
        let action = values.follow_up_action || '';
        let notes = (values.follow_up_notes || '').trim();

        if (!action) {
            frappe.msgprint({
                title: 'Action Required',
                message: 'Please select a manager follow-up action.',
                indicator: 'orange'
            });
            return;
        }

        frappe.call({
            method: 'care_management.care_management.page.manager_dashboard.manager_dashboard.validate_manager_follow_up_decision',
            args: {
                execution_instance: execution_instance,
                follow_up_action: action,
                manager_notes: notes
            },
            freeze: true,
            freeze_message: 'Validating manager review...',
            callback: function(r) {
                if (r.exc) return;
                let result = r.message || {};

                if (action === 'Acknowledge') {
                    frappe.show_alert({ message: 'Manager review acknowledged.', indicator: 'green' });
                    dialog.hide();
                    me.load_dashboard();
                    return;
                }

                if (action === 'Mark No Follow-up Required') {
                    frappe.show_alert({ message: 'Follow-up requirement cleared.', indicator: 'green' });
                    dialog.hide();
                    me.load_dashboard();
                    return;
                }

                if (action === 'Create Follow-up') {
                    dialog.hide();
                    me.open_create_follow_up_dialog(execution_instance, result);
                    return;
                }
            }
        });
    }

    // ================================================================
    // CREATE FOLLOW-UP DIALOG
    // ================================================================
    open_create_follow_up_dialog(execution_instance, validation_result) {
        let me = this;
        let d = new frappe.ui.Dialog({
            title: 'Create Manager Follow-up',
            size: 'large',
            fields: [
                {
                    fieldname: 'execution_instance',
                    fieldtype: 'Data',
                    label: 'Execution Instance',
                    default: execution_instance,
                    read_only: 1
                },
                {
                    fieldname: 'follow_up_reason',
                    fieldtype: 'Select',
                    label: 'Follow-up Reason',
                    options: '\nMissed Task\nParticipant Unavailable\nService Exception\nStaff Issue\nSafety Concern\nDocumentation Issue\nOther',
                    reqd: 1
                },
                {
                    fieldname: 'priority',
                    fieldtype: 'Select',
                    label: 'Priority',
                    options: 'Low\nMedium\nHigh\nCritical',
                    default: 'Medium',
                    reqd: 1
                },
                {
                    fieldname: 'description',
                    fieldtype: 'Small Text',
                    label: 'Follow-up Description',
                    reqd: 1
                },
                {
                    fieldname: 'assigned_to',
                    fieldtype: 'Link',
                    label: 'Assigned To',
                    options: 'User',
                    default: frappe.session.user,
                    reqd: 1
                },
                {
                    fieldname: 'due_date',
                    fieldtype: 'Date',
                    label: 'Due Date',
                    default: frappe.datetime.add_days(frappe.datetime.get_today(), 1),
                    reqd: 1
                },
                {
                    fieldname: 'due_time',
                    fieldtype: 'Time',
                    label: 'Due Time'
                },
                {
                    fieldname: 'manager_notes',
                    fieldtype: 'Small Text',
                    label: 'Manager Notes',
                    reqd: 1
                }
            ],
            primary_action_label: 'Create Follow-up',
            primary_action: function(values) {
                if (!values.follow_up_reason) {
                    frappe.msgprint('Please select a follow-up reason.');
                    return;
                }
                if (!values.priority) {
                    frappe.msgprint('Please select a priority.');
                    return;
                }
                if (!values.description) {
                    frappe.msgprint('Please enter a follow-up description.');
                    return;
                }
                if (!values.assigned_to) {
                    frappe.msgprint('Please select who this follow-up is assigned to.');
                    return;
                }
                if (!values.due_date) {
                    frappe.msgprint('Please select a due date.');
                    return;
                }
                if (!values.manager_notes) {
                    frappe.msgprint('Manager Notes are required.');
                    return;
                }

                frappe.call({
                    method: 'care_management.care_management.page.manager_dashboard.manager_dashboard.create_manager_follow_up',
                    args: {
                        execution_instance: values.execution_instance || execution_instance,
                        follow_up_reason: values.follow_up_reason,
                        priority: values.priority,
                        description: values.description,
                        assigned_to: values.assigned_to,
                        due_date: values.due_date,
                        due_time: values.due_time,
                        manager_notes: values.manager_notes
                    },
                    freeze: true,
                    freeze_message: 'Creating manager follow-up...',
                    callback: function(r) {
                        if (r.exc) return;
                        let result = r.message || {};

                        if (result.duplicate) {
                            frappe.msgprint({
                                title: 'Follow-up Already Exists',
                                message: `An active follow-up already exists: <b>${frappe.utils.escape_html(result.follow_up.name)}</b>`,
                                indicator: 'orange'
                            });
                            d.hide();
                            me.load_dashboard();
                            return;
                        }

                        if (result.created) {
                            frappe.show_alert({
                                message: `Follow-up ${frappe.utils.escape_html(result.follow_up.name)} created successfully.`,
                                indicator: 'green'
                            });
                            d.hide();
                            me.load_dashboard();
                            return;
                        }

                        frappe.msgprint({
                            title: 'Follow-up Not Created',
                            message: 'The follow-up could not be created.',
                            indicator: 'red'
                        });
                    }
                });
            }
        });

        d.show();
    }

    // ================================================================
    // DISPLAY VALUE
    // ================================================================
    display_value(value) {
        if (value === null || value === undefined || value === '') {
            return '-';
        }
        return String(value);
    }

    // ================================================================
    // RENDER REVIEWS
    // ================================================================
    render_reviews(reviews) {
        let me = this;

        if (!reviews || !reviews.length) {
            $('#manager-dashboard-results').html(`
                <div class="manager-empty-state">
                    No execution records require review for the selected filters.
                </div>
            `);
            return;
        }

        let priority_order = { 'High': 1, 'Medium': 2, 'Low': 3 };
        reviews.sort(function(a, b) {
            return (priority_order[a.review_priority] || 99) - (priority_order[b.review_priority] || 99);
        });

        let html = '';
        reviews.forEach(function(row) {
            let priority = row.review_priority || 'Low';
            let priority_badge = priority === 'High' ? 'badge-high' : priority === 'Medium' ? 'badge-med' : 'badge-low';
            let execution_instance = me.safe(row.execution_instance);
            let support_task = me.safe(row.support_task);
            let participant = me.safe(row.participant || 'Participant not set');
            let task_name = me.safe(row.task_name || 'Support Task');
            let scheduled_date = me.safe(row.scheduled_date);
            let scheduled_time = me.safe(row.scheduled_time);
            let status = me.safe(row.status);
            let category = me.safe(row.review_category);
            let exception_type = me.safe(row.exception_type);
            let follow_up = row.follow_up_required ? 'Required' : 'No';

            html += `
                <div class="manager-review-card ${me.review_tone_class(row)}" data-execution-instance="${execution_instance}">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px;">
                        <div>
                            <div class="manager-review-title">${task_name}</div>
                            <div class="manager-review-meta"><i class="fa fa-user-circle" style="margin-right:4px;"></i>${participant}</div>
                        </div>
                        <span class="manager-badge ${priority_badge}">${me.safe(priority)}</span>
                    </div>

                    <div class="manager-review-grid">
                        <div><strong>Execution:</strong> ${execution_instance}</div>
                        <div><strong>Support Task:</strong> ${support_task}</div>
                        <div><strong>Date:</strong> ${scheduled_date}</div>
                        <div><strong>Time:</strong> ${scheduled_time}</div>
                        <div><strong>Status:</strong> ${status}</div>
                        <div><strong>Category:</strong> ${category}</div>
                        <div><strong>Follow-up:</strong> ${follow_up}</div>
                    </div>

                    ${exception_type ? `
                        <div style="margin-top:8px; padding:6px 10px; background:rgba(254, 226, 226, 0.8); border-radius:6px; font-size:11px; color:#991b1b;">
                            <strong>Exception:</strong> ${exception_type}
                        </div>
                    ` : ''}
                </div>
            `;
        });

        $('#manager-dashboard-results').html(html);

        $('.manager-review-card').on('click', function() {
            let execution_instance = $(this).attr('data-execution-instance');
            if (!execution_instance) return;

            frappe.msgprint({
                title: 'Manager Review',
                message: `
                    <p><strong>Execution Instance:</strong> ${frappe.utils.escape_html(execution_instance)}</p>
                    <p>This execution record is available for manager review.</p>
                `,
                indicator: 'blue'
            });
        });
    }

    // ================================================================
    // SAFE HTML VALUE
    // ================================================================
    safe(value) {
        if (value === null || value === undefined || value === '') {
            return '-';
        }
        return frappe.utils.escape_html(String(value));
    }

    // ================================================================
    // CARD TONE HELPERS
    // ================================================================
    review_tone_class(row) {
        let category = (row && row.review_category) || '';
        if (category === 'Completed') return 'card-tone-success';
        if (category === 'Missed' || category === 'Exception') return 'card-tone-danger';
        if (category === 'Follow-up') return 'card-tone-warning';
        if (category === 'In Progress') return 'card-tone-info';
        return 'card-tone-neutral';
    }

    follow_up_tone_class(row) {
        let status = (row && row.status) || '';
        if (status === 'Resolved') return 'card-tone-success';
        if (status === 'Cancelled') return 'card-tone-neutral';
        if (row && (row.priority === 'High' || row.priority === 'Critical')) return 'card-tone-danger';
        return 'card-tone-warning';
    }
}