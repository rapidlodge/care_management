frappe.pages['manager-dashboard'].on_page_load = function(wrapper) {

    let page = frappe.ui.make_app_page({

        parent: wrapper,

        title: 'Manager Dashboard',

        single_column: true

    });


    wrapper.manager_dashboard =
        new ManagerDashboard(page);

};


class ManagerDashboard {

    constructor(page) {

        this.page = page;

        this.start_date =
            moment().startOf('day').format('YYYY-MM-DD');

        this.end_date =
            moment().endOf('day').format('YYYY-MM-DD');

        this.status =
            '';

        this.attention_type =
            'all';

        this.make_layout();

        this.load_dashboard();

    }


    // ================================================================
    // PAGE LAYOUT
    // ================================================================

    make_layout() {

        let me = this;


        this.page.set_primary_action(
            'Refresh',
            function() {

                me.load_dashboard();

            }
        );


        let html = `

            <style>

                .manager-dashboard {

                    padding:
                        10px 5px 30px 5px;

                }


                .manager-dashboard
                .dashboard-header {

                    margin-bottom:
                        15px;

                }


                .manager-dashboard
                .dashboard-title {

                    font-size:
                        18px;

                    font-weight:
                        700;

                }


                .manager-dashboard
                .dashboard-subtitle {

                    color:
                        #6c757d;

                    font-size:
                        12px;

                    margin-top:
                        3px;

                }


                .manager-filter-bar {

                    background:
                        #f8f9fa;

                    border:
                        1px solid #d9dee3;

                    border-radius:
                        6px;

                    padding:
                        12px;

                    margin-bottom:
                        15px;

                }


                .manager-filter-grid {

                    display:
                        grid;

                    grid-template-columns:
                        repeat(
                            auto-fit,
                            minmax(
                                180px,
                                1fr
                            )
                        );

                    gap:
                        10px;

                    align-items:
                        end;

                }


                .manager-filter-label {

                    display:
                        block;

                    font-size:
                        11px;

                    font-weight:
                        600;

                    margin-bottom:
                        4px;

                }


                .manager-kpi-grid {

                    display:
                        grid;

                    grid-template-columns:
                        repeat(
                            auto-fit,
                            minmax(
                                150px,
                                1fr
                            )
                        );

                    gap:
                        10px;

                    margin-bottom:
                        15px;

                }


                .manager-kpi-card {

                    border:
                        1px solid #d9dee3;

                    border-radius:
                        6px;

                    background:
                        #ffffff;

                    padding:
                        14px;

                    min-height:
                        85px;

                }


                .manager-kpi-label {

                    font-size:
                        11px;

                    color:
                        #6c757d;

                }


                .manager-kpi-value {

                    font-size:
                        24px;

                    font-weight:
                        700;

                    margin-top:
                        5px;

                }


                .manager-section {

                    border:
                        1px solid #d9dee3;

                    border-radius:
                        6px;

                    background:
                        #ffffff;

                    margin-bottom:
                        15px;

                    overflow:
                        hidden;

                }


                .manager-section-header {

                    padding:
                        11px 14px;

                    background:
                        #f8f9fa;

                    border-bottom:
                        1px solid #d9dee3;

                    font-weight:
                        700;

                }


                .manager-section-body {

                    padding:
                        12px;

                }


                .manager-review-card {

                    border:
                        1px solid #d9dee3;

                    border-radius:
                        6px;

                    padding:
                        12px;

                    margin-bottom:
                        8px;

                    background:
                        #ffffff;

                    cursor:
                        pointer;

                    transition:
                        box-shadow 0.15s ease;

                }


                .manager-review-card:hover {

                    box-shadow:
                        0 2px 8px
                        rgba(0,0,0,0.08);

                }


                .manager-review-title {

                    font-weight:
                        700;

                    font-size:
                        13px;

                }


                .manager-review-meta {

                    color:
                        #6c757d;

                    font-size:
                        11px;

                    margin-top:
                        3px;

                }


                .manager-review-grid {

                    display:
                        grid;

                    grid-template-columns:
                        repeat(
                            auto-fit,
                            minmax(
                                150px,
                                1fr
                            )
                        );

                    gap:
                        8px 15px;

                    margin-top:
                        10px;

                    font-size:
                        11px;

                }


                .manager-empty-state {

                    padding:
                        30px;

                    text-align:
                        center;

                    color:
                        #6c757d;

                }


                .manager-loading {

                    padding:
                        30px;

                    text-align:
                        center;

                    color:
                        #6c757d;

                }


                @media (
                    max-width: 768px
                ) {

                    .manager-filter-grid {

                        grid-template-columns:
                            1fr;

                    }

                    .manager-kpi-grid {

                        grid-template-columns:
                            repeat(
                                2,
                                1fr
                            );

                    }

                }

            </style>


            <div
                class="manager-dashboard"
            >

                <div
                    class="dashboard-header"
                >

                    <div
                        class="dashboard-title"
                    >
                        Manager Dashboard
                    </div>

                    <div
                        class="dashboard-subtitle"
                    >
                        Operational oversight,
                        execution review and
                        follow-up management.
                    </div>

                </div>


                <!-- ==================================================
                     FILTERS
                     ================================================== -->

                <div
                    class="manager-filter-bar"
                >

                    <div
                        class="manager-filter-grid"
                    >

                        <div>

                            <label
                                class="manager-filter-label"
                            >
                                Start Date
                            </label>

                            <input
                                type="date"
                                id="manager-dashboard-start-date"
                                class="form-control input-sm"
                            >

                        </div>


                        <div>

                            <label
                                class="manager-filter-label"
                            >
                                End Date
                            </label>

                            <input
                                type="date"
                                id="manager-dashboard-end-date"
                                class="form-control input-sm"
                            >

                        </div>


                        <div>

                            <label
                                class="manager-filter-label"
                            >
                                Status
                            </label>

                            <select
                                id="manager-dashboard-status"
                                class="form-control input-sm"
                            >

                                <option value="">
                                    All
                                </option>

                                <option value="In Progress">
                                    In Progress
                                </option>

                                <option value="Completed">
                                    Completed
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

                            </select>

                        </div>


                        <div>

                            <button
                                class="
                                    btn
                                    btn-primary
                                    btn-sm
                                "
                                id="manager-dashboard-apply"
                                style="
                                    width: 100%;
                                "
                            >
                                <i
                                    class="fa fa-filter"
                                ></i>

                                Apply Filters

                            </button>

                        </div>

                    </div>

                </div>


                <!-- ==================================================
                     KPI AREA
                     ================================================== -->

                <div
                    id="manager-dashboard-kpis"
                    class="manager-kpi-grid"
                ></div>

                <!-- =========================================================
                     NEEDS ATTENTION
                     ========================================================= -->

                
                <div
                    class="manager-section"
                >

                    <div
                        class="manager-section-header"
                        style="
                            display: flex;
                            justify-content: space-between;
                            align-items: center;
                        "
                    >

                        <span>
                            Needs Attention
                        </span>

                        <span
                            id="manager-attention-count"
                            class="text-muted"
                            style="
                                font-size: 11px;
                                font-weight: normal;
                            "
                        >
                            0 items
                        </span>

                    </div>

                    <div
                        style="
                            display: flex;
                            gap: 6px;
                            margin-bottom: 12px;
                            flex-wrap: wrap;
                        "
                    >

                        <button
                            type="button"
                            class="
                                btn
                                btn-xs
                                btn-default
                                manager-attention-filter
                                active
                            "
                            data-attention-type="all"
                        >
                            All
                        </button>

                        <button
                            type="button"
                            class="
                                btn
                                btn-xs
                                btn-default
                                manager-attention-filter
                            "
                            data-attention-type="follow_up"
                        >
                            Follow-up
                        </button>

                        <button
                            type="button"
                            class="
                                btn
                                btn-xs
                                btn-default
                                manager-attention-filter
                            "
                            data-attention-type="missed"
                        >
                            Missed
                        </button>

                        <button
                            type="button"
                            class="
                                btn
                                btn-xs
                                btn-default
                                manager-attention-filter
                            "
                            data-attention-type="exception"
                        >
                            Exceptions
                        </button>

                    </div>

                    <div
                        id="manager-attention-results"
                        class="manager-section-body"
                    >

                        <div
                            class="manager-loading"
                        >
                            Loading...
                        </div>

                    </div>

                </div>


                <!-- ==================================================
                     MANAGER REVIEW
                     ================================================== -->

                <div
                    class="manager-section"
                >

                    <div
                        class="manager-section-header"
                    >

                        Manager Review

                    </div>


                    <div
                        id="manager-dashboard-results"
                        class="manager-section-body"
                    ></div>

                </div>

                <div
                    class="manager-section"
                >

                    <div
                        class="manager-section-header"
                        style="
                            display:flex;
                            justify-content:space-between;
                            align-items:center;
                        "
                    >

                        <span>
                            Open Follow-ups
                        </span>

                        <span
                            id="manager-follow-up-count"
                            class="text-muted"
                            style="
                                font-size:11px;
                                font-weight:normal;
                            "
                        >
                            0 items
                        </span>

                    </div>

                    <div
                        id="manager-follow-up-results"
                        class="manager-section-body"
                    >
                        <div
                            class="manager-loading"
                        >
                            Loading...
                        </div>
                    </div>

                </div>

            </div>

        `;


        $(this.page.body)
            .html(html);

        this.bind_attention_filters();

        this.load_attention_items();


        $('#manager-dashboard-start-date')
            .val(
                this.start_date
            );


        $('#manager-dashboard-end-date')
            .val(
                this.end_date
            );


        $('#manager-dashboard-status')
            .val(
                this.status
            );


        $('#manager-dashboard-apply')
            .on(
                'click',
                function() {

                    me.apply_filters();

                }
            );


    }


    // ================================================================
    // BIND ATTENTION FILTERS
    // ================================================================

    bind_attention_filters() {

        let me = this;

        $(this.page.body)
            .off(
                'click.manager_attention',
                '.manager-attention-filter'
            );

        $(this.page.body)
            .on(
                'click.manager_attention',
                '.manager-attention-filter',
                function() {

                    let attention_type =
                        $(this).attr(
                            'data-attention-type'
                        );

                    if (
                        !attention_type
                    ) {

                        attention_type =
                            'all';

                    }

                    me.attention_type =
                        attention_type;

                    $(me.page.body)
                        .find(
                            '.manager-attention-filter'
                        )
                        .removeClass(
                            'active'
                        );

                    $(this)
                        .addClass(
                            'active'
                        );

                    me.load_attention_items();

                }
            );

    }


    // ================================================================
    // APPLY FILTERS
    // ================================================================

    apply_filters() {

        let start_date =
            $('#manager-dashboard-start-date')
                .val();


        let end_date =
            $('#manager-dashboard-end-date')
                .val();


        let status =
            $('#manager-dashboard-status')
                .val();


        if (
            !start_date ||
            !end_date
        ) {

            frappe.msgprint(
                'Please select both Start Date and End Date.'
            );

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


        this.start_date =
            start_date;


        this.end_date =
            end_date;


        this.status =
            status || '';


        this.load_dashboard();

    }


    get_start_date() {

        return (
            $('#manager-dashboard-start-date')
                .val() ||
            this.start_date
        );

    }


    get_end_date() {

        return (
            $('#manager-dashboard-end-date')
                .val() ||
            this.end_date
        );

    }


    // ================================================================
    // LOAD DASHBOARD
    // ================================================================

    load_dashboard() {

        let me = this;


        $('#manager-dashboard-results')
            .html(`

                <div
                    class="manager-loading"
                >

                    <i
                        class="fa fa-spinner fa-spin"
                    ></i>

                    Loading manager review...

                </div>

            `);


        $('#manager-dashboard-kpis')
            .html('');


        frappe.call({

            method:
                'care_management.care_management.page.manager_dashboard.manager_dashboard.get_manager_dashboard_data',

            args: {

                start_date:
                    this.start_date,

                end_date:
                    this.end_date,

                status:
                    this.status || null

            },

            callback:
                function(r) {

                    if (
                        r.exc
                    ) {

                        $('#manager-dashboard-results')
                            .html(`

                                <div
                                    class="
                                        text-danger
                                        manager-empty-state
                                    "
                                >
                                    Unable to load
                                    Manager Dashboard.
                                </div>

                            `);

                        return;
                    }


                    let data =
                        r.message || {};


                    let kpis =
                        data.kpis || {};

                    if (
                        data.follow_up_count != null
                    ) {

                        kpis.follow_up =
                            data.follow_up_count;

                    }

                    me.render_kpis(
                        kpis
                    );


                    me.load_attention_items();


                    me.render_reviews(
                        data.reviews || []
                    );

                    me.load_follow_ups();

                }

        });

    }


    // ================================================================
    // LOAD ATTENTION ITEMS
    // ================================================================

    load_attention_items() {

        let me = this;

        $('#manager-attention-results')
            .html(`
                <div
                    class="manager-loading"
                    style="
                        padding: 20px;
                        text-align: center;
                        color: #888;
                    "
                >
                    Loading...
                </div>
            `);

        frappe.call({

            method:
                'care_management.care_management.page.manager_dashboard.manager_dashboard.get_manager_attention_items',

            args: {

                start_date:
                    me.get_start_date(),

                end_date:
                    me.get_end_date(),

                attention_type:
                    me.attention_type || 'all',

                limit:
                    50

            },

            callback:
                function(r) {

                    if (
                        r.exc
                    ) {

                        $('#manager-attention-results')
                            .html(`
                                <div
                                    style="
                                        padding: 20px;
                                        text-align: center;
                                        color: #d63939;
                                    "
                                >
                                    Unable to load attention items.
                                </div>
                            `);

                        return;
                    }

                    let items =
                        r.message || [];

                    me.render_attention_items(
                        items
                    );

                },

            error:
                function() {

                    $('#manager-attention-results')
                        .html(`
                            <div
                                style="
                                    padding: 20px;
                                    text-align: center;
                                    color: #d63939;
                                "
                            >
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

        $('#manager-follow-up-results')
            .html(`
                <div
                    class="manager-loading"
                >
                    <i
                        class="fa fa-spinner fa-spin"
                    ></i>

                    Loading follow-ups...
                </div>
            `);

        frappe.call({

            method:
                'care_management.care_management.page.manager_dashboard.manager_dashboard.get_manager_follow_ups',

            args: {

                status:
                    '',

                start_date:
                    me.get_start_date(),

                end_date:
                    me.get_end_date(),

                limit:
                    50
            },

            callback:
                function(r) {

                    if (
                        r.exc
                    ) {

                        $('#manager-follow-up-results')
                            .html(`
                                <div
                                    class="text-danger manager-empty-state"
                                >
                                    Unable to load follow-ups.
                                </div>
                            `);

                        return;
                    }

                    me.render_follow_ups(
                        r.message || []
                    );
                },

            error:
                function() {

                    $('#manager-follow-up-results')
                        .html(`
                            <div
                                class="text-danger manager-empty-state"
                            >
                                Unable to load follow-ups.
                            </div>
                        `);
                }
        });
    }


    // ================================================================
    // RENDER FOLLOW-UPS
    // ================================================================

    render_follow_ups(
        follow_ups
    ) {

        let me = this;

        follow_ups =
            follow_ups || [];

        $('#manager-follow-up-count')
            .text(
                `${follow_ups.length} item${
                    follow_ups.length === 1
                        ? ''
                        : 's'
                }`
            );

        if (
            !follow_ups.length
        ) {

            $('#manager-follow-up-results')
                .html(`
                    <div
                        class="manager-empty-state"
                    >
                        <i
                            class="fa fa-check-circle"
                            style="
                                font-size:20px;
                                margin-bottom:8px;
                            "
                        ></i>

                        <div>
                            No open follow-ups.
                        </div>
                    </div>
                `);

            return;
        }

        let html = '';

        follow_ups.forEach(
            function(row) {

                let priority =
                    me.safe(
                        row.priority
                    );

                let status =
                    me.safe(
                        row.status
                    );

                let participant =
                    me.safe(
                        row.participant ||
                        'Participant not set'
                    );

                let task =
                    me.safe(
                        row.support_task ||
                        'Support Task'
                    );

                let assigned =
                    me.safe(
                        row.assigned_to
                    );

                let due_date =
                    me.safe(
                        row.due_date
                    );

                let reason =
                    me.safe(
                        row.follow_up_reason
                    );

                html += `
                    <div
                        class="manager-review-card"
                        data-follow-up-name="${me.safe(
                            row.name
                        )}"
                    >

                        <div
                            style="
                                display:flex;
                                justify-content:space-between;
                                gap:10px;
                            "
                        >

                            <div>

                                <div
                                    class="manager-review-title"
                                >
                                    ${task}
                                </div>

                                <div
                                    class="manager-review-meta"
                                >
                                    ${participant}
                                </div>

                            </div>

                            <div
                                style="
                                    font-size:11px;
                                    font-weight:700;
                                "
                            >
                                ${priority}
                            </div>

                        </div>

                        <div
                            class="manager-review-grid"
                        >

                            <div>
                                <strong>
                                    Follow-up:
                                </strong>

                                ${me.safe(row.name)}
                            </div>

                            <div>
                                <strong>
                                    Reason:
                                </strong>

                                ${reason}
                            </div>

                            <div>
                                <strong>
                                    Assigned:
                                </strong>

                                ${assigned}
                            </div>

                            <div>
                                <strong>
                                    Due:
                                </strong>

                                ${due_date}
                            </div>

                            <div>
                                <strong>
                                    Status:
                                </strong>

                                ${status}
                            </div>

                        </div>

                    </div>
                `;
            }
        );

        $('#manager-follow-up-results')
            .html(html);
    }


    // ================================================================
    // RENDER KPI
    // ================================================================

    render_kpis(
        kpis
    ) {

        let cards = [

            {
                label:
                    'Total',

                value:
                    kpis.total || 0
            },


            {
                label:
                    'Completed',

                value:
                    kpis.completed || 0
            },


            {
                label:
                    'Missed',

                value:
                    kpis.missed || 0
            },


            {
                label:
                    'Exceptions',

                value:
                    kpis.exceptions || 0
            },


            {
                label:
                    'Follow-up',

                value:
                    kpis.follow_up_count != null
                        ? kpis.follow_up_count
                        : kpis.follow_up || 0
            },


            {
                label:
                    'In Progress',

                value:
                    kpis.in_progress || 0
            }

        ];


        let html = '';


        cards.forEach(
            function(card) {

                html += `

                    <div
                        class="manager-kpi-card"
                    >

                        <div
                            class="manager-kpi-label"
                        >
                            ${frappe.utils.escape_html(
                                card.label
                            )}
                        </div>


                        <div
                            class="manager-kpi-value"
                        >
                            ${card.value}
                        </div>

                    </div>

                `;

            }
        );


        $('#manager-dashboard-kpis')
            .html(html);

    }


    // ================================================================
    // RENDER NEEDS ATTENTION
    // ================================================================

    render_attention_items(
        items
    ) {

        let me = this;

        items =
            items || [];

        $('#manager-attention-count')
            .text(
                `${items.length} item${
                    items.length === 1
                        ? ''
                        : 's'
                }`
            );

        if (
            !items.length
        ) {

            $('#manager-attention-results')
                .html(`

                    <div
                        class="manager-empty-state"
                    >

                        <i
                            class="fa fa-check-circle"
                            style="
                                font-size: 20px;
                                margin-bottom: 8px;
                            "
                        ></i>

                        <div>
                            No items currently
                            require manager attention.
                        </div>

                    </div>

                `);

            return;
        }

        let html = '';

        items.forEach(
            function(row) {

                let priority =
                    row.review_priority ||
                    'Low';

                let priority_class =
                    priority === 'High'
                        ? 'text-danger'
                        : priority === 'Medium'
                            ? 'text-warning'
                            : 'text-muted';

                let task_name =
                    me.safe(
                        row.task_name ||
                        'Support Task'
                    );

                let participant =
                    me.safe(
                        row.participant ||
                        'Participant not set'
                    );

                let status =
                    me.safe(
                        row.status
                    );

                let category =
                    me.safe(
                        row.review_category
                    );

                let reason =
                    me.safe(
                        row.attention_reason
                    );

                let date =
                    me.safe(
                        row.scheduled_date
                    );

                let time =
                    me.safe(
                        row.scheduled_time
                    );

                let execution_instance =
                    me.safe(
                        row.execution_instance
                    );

                html += `

                    <div
                        class="manager-review-card"
                        data-execution-instance="
                            ${execution_instance}
                        "
                        style="
                            border-left:
                                4px solid
                                ${
                                    priority === 'High'
                                        ? '#d63939'
                                        : priority === 'Medium'
                                            ? '#f0ad4e'
                                            : '#6c757d'
                                };
                        "
                    >

                        <div
                            style="
                                display:
                                    flex;

                                justify-content:
                                    space-between;

                                align-items:
                                    flex-start;

                                gap:
                                    10px;
                            "
                        >

                            <div>

                                <div
                                    class="
                                        manager-review-title
                                    "
                                >
                                    ${task_name}
                                </div>

                                <div
                                    class="
                                        manager-review-meta
                                    "
                                >
                                    ${participant}
                                </div>

                            </div>

                            <div
                                class="${priority_class}"
                                style="
                                    font-size: 10px;
                                    font-weight: 700;
                                    white-space: nowrap;
                                "
                            >

                                ${me.safe(
                                    priority
                                )}

                            </div>

                        </div>

                        <div
                            style="
                                margin-top: 8px;
                                font-size: 11px;
                            "
                        >

                            <strong>
                                Attention:
                            </strong>

                            ${reason}

                        </div>

                        <div
                            class="
                                manager-review-grid
                            "
                        >

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
                                    Date:
                                </strong>

                                ${date}

                            </div>

                            <div>

                                <strong>
                                    Time:
                                </strong>

                                ${time}

                            </div>

                        </div>

                    </div>

                `;

            }
        );

        $('#manager-attention-results')
            .html(
                html
            );

        $('#manager-attention-results')
            .find(
                '.manager-review-card'
            )
            .on(
                'click',
                function() {

                    let execution_instance =
                        $(this).attr(
                            'data-execution-instance'
                        );

                    if (
                        !execution_instance
                    ) {

                        return;
                    }

                    me.open_execution_review(
                        execution_instance
                    );

                }
            );
    }


    // ================================================================
    // OPEN EXECUTION REVIEW
    // ================================================================

    open_execution_review(
        execution_instance
    ) {

        let me = this;

        let dialog =
            new frappe.ui.Dialog({

                title:
                    'Manager Execution Review',

                size:
                    'large',

                primary_action_label:
                    'Save Review',

                primary_action:
                    function(values) {

                        me.save_manager_review(
                            execution_instance,
                            values,
                            dialog
                        );

                    },

                fields: [

                    {
                        fieldname:
                            'execution_instance',

                        fieldtype:
                            'Data',

                        label:
                            'Execution Instance',

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'support_task',

                        fieldtype:
                            'Data',

                        label:
                            'Support Task',

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'task_name',

                        fieldtype:
                            'Data',

                        label:
                            'Task',

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'participant',

                        fieldtype:
                            'Data',

                        label:
                            'Participant',

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'staff',

                        fieldtype:
                            'Data',

                        label:
                            'Assigned Staff',

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'scheduled_date',

                        fieldtype:
                            'Date',

                        label:
                            'Scheduled Date',

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'scheduled_time',

                        fieldtype:
                            'Time',

                        label:
                            'Scheduled Time',

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'status',

                        fieldtype:
                            'Data',

                        label:
                            'Status',

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'review_category',

                        fieldtype:
                            'Data',

                        label:
                            'Review Category',

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'review_priority',

                        fieldtype:
                            'Data',

                        label:
                            'Review Priority',

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'exception_type',

                        fieldtype:
                            'Data',

                        label:
                            'Exception',

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'follow_up_required',

                        fieldtype:
                            'Check',

                        label:
                            'Follow-up Required',

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'notes',

                        fieldtype:
                            'Small Text',

                        label:
                            'Notes',

                        read_only:
                            1
                    },
                    {
                        fieldname:
                            'follow_up_section',

                        fieldtype:
                            'Section Break',

                        label:
                            'Follow-up'
                    },


                    {
                        fieldname:
                            'follow_up_action',

                        fieldtype:
                            'Select',

                        label:
                            'Manager Follow-up Action',

                        options:
                            [
                                '',
                                'Acknowledge',
                                'Create Follow-up',
                                'Mark No Follow-up Required'
                            ].join('\n'),

                        default:
                            ''
                    },


                    {
                        fieldname:
                            'follow_up_notes',

                        fieldtype:
                            'Small Text',

                        label:
                            'Manager Notes'
                    }

                ]

            });

        dialog.show();

        // ------------------------------------------------------------
        // Loading state
        // ------------------------------------------------------------

        dialog.set_df_property(
            'execution_instance',
            'description',
            'Loading execution review...'
        );

        frappe.call({

            method:
                'care_management.care_management.page.manager_dashboard.manager_dashboard.get_execution_review_detail',

            args: {

                execution_instance:
                    execution_instance

            },

            callback:
                function(r) {

                    if (
                        r.exc
                    ) {

                        dialog.hide();

                        frappe.msgprint({

                            title:
                                'Unable to Load Review',

                            message:
                                'The execution review could not be loaded.',

                            indicator:
                                'red'

                        });

                        return;
                    }

                    let data =
                        r.message || {};

                    dialog.set_values({

                        execution_instance:
                            me.display_value(
                                data.execution_instance
                            ),

                        support_task:
                            me.display_value(
                                data.support_task
                            ),

                        task_name:
                            me.display_value(
                                data.task_name
                            ),

                        participant:
                            me.display_value(
                                data.participant
                            ),

                        staff:
                            me.display_value(
                                data.staff
                            ),

                        scheduled_date:
                            data.scheduled_date || '',

                        scheduled_time:
                            data.scheduled_time || '',

                        status:
                            me.display_value(
                                data.status
                            ),

                        review_category:
                            me.display_value(
                                data.review_category
                            ),

                        review_priority:
                            me.display_value(
                                data.review_priority
                            ),

                        exception_type:
                            me.display_value(
                                data.exception_type
                            ),

                        follow_up_required:
                            data.follow_up_required
                                ? 1
                                : 0,

                        notes:
                            me.display_value(
                                data.notes
                            )

                    });

                    dialog.set_df_property(
                        'execution_instance',
                        'description',
                        ''
                    );

                }

        });

    }
    // ================================================================
    // ================================================================
    // SAVE MANAGER REVIEW
    // ================================================================

    save_manager_review(
        execution_instance,
        values,
        dialog
    ) {
        let me = this;

        let action =
            values.follow_up_action || '';

        let notes =
            (
                values.follow_up_notes ||
                ''
            ).trim();

        if (!action) {

            frappe.msgprint({
                title:
                    'Action Required',

                message:
                    'Please select a manager follow-up action.',

                indicator:
                    'orange'
            });

            return;
        }

        frappe.call({
            method:
                'care_management.care_management.page.manager_dashboard.manager_dashboard.validate_manager_follow_up_decision',

            args: {
                execution_instance:
                    execution_instance,

                follow_up_action:
                    action,

                manager_notes:
                    notes
            },

            freeze:
                true,

            freeze_message:
                'Validating manager review...',

            callback:
                function(r) {

                    if (
                        r.exc
                    ) {
                        return;
                    }

                    let result =
                        r.message || {};

                    // ----------------------------------------------------
                    // ACKNOWLEDGE
                    // ----------------------------------------------------

                    if (
                        action ===
                        'Acknowledge'
                    ) {

                        frappe.show_alert({
                            message:
                                'Manager review acknowledged.',

                            indicator:
                                'green'
                        });

                        dialog.hide();

                        me.load_dashboard();

                        return;
                    }

                    // ----------------------------------------------------
                    // NO FOLLOW-UP
                    // ----------------------------------------------------

                    if (
                        action ===
                        'Mark No Follow-up Required'
                    ) {

                        frappe.show_alert({
                            message:
                                'Follow-up requirement cleared.',

                            indicator:
                                'green'
                        });

                        dialog.hide();

                        me.load_dashboard();

                        return;
                    }

                    // ----------------------------------------------------
                    // CREATE FOLLOW-UP
                    // ----------------------------------------------------

                    if (
                        action ===
                        'Create Follow-up'
                    ) {

                        dialog.hide();

                        me.open_create_follow_up_dialog(
                            execution_instance,
                            result
                        );

                        return;
                    }
                }
        });
    }
    
    
    // ================================================================
    // CREATE FOLLOW-UP DIALOG
    // ================================================================

    open_create_follow_up_dialog(
        execution_instance,
        validation_result
    ) {
        let me = this;

        let d =
            new frappe.ui.Dialog({

                title:
                    'Create Manager Follow-up',

                size:
                    'large',

                fields: [

                    {
                        fieldname:
                            'execution_instance',

                        fieldtype:
                            'Data',

                        label:
                            'Execution Instance',

                        default:
                            execution_instance,

                        read_only:
                            1
                    },

                    {
                        fieldname:
                            'follow_up_reason',

                        fieldtype:
                            'Select',

                        label:
                            'Follow-up Reason',

                        options:
                            '\nMissed Task\nParticipant Unavailable\nService Exception\nStaff Issue\nSafety Concern\nDocumentation Issue\nOther',

                        reqd:
                            1
                    },

                    {
                        fieldname:
                            'priority',

                        fieldtype:
                            'Select',

                        label:
                            'Priority',

                        options:
                            'Low\nMedium\nHigh\nCritical',

                        default:
                            'Medium',

                        reqd:
                            1
                    },

                    {
                        fieldname:
                            'description',

                        fieldtype:
                            'Small Text',

                        label:
                            'Follow-up Description',

                        reqd:
                            1
                    },

                    {
                        fieldname:
                            'assigned_to',

                        fieldtype:
                            'Link',

                        label:
                            'Assigned To',

                        options:
                            'User',

                        default:
                            frappe.session.user,

                        reqd:
                            1
                    },

                    {
                        fieldname:
                            'due_date',

                        fieldtype:
                            'Date',

                        label:
                            'Due Date',

                        default:
                            frappe.datetime.add_days(
                                frappe.datetime.get_today(),
                                1
                            ),

                        reqd:
                            1
                    },

                    {
                        fieldname:
                            'due_time',

                        fieldtype:
                            'Time',

                        label:
                            'Due Time'
                    },

                    {
                        fieldname:
                            'manager_notes',

                        fieldtype:
                            'Small Text',

                        label:
                            'Manager Notes',

                        reqd:
                            1
                    }
                ],

                primary_action_label:
                    'Create Follow-up',

                primary_action:
                    function(values) {

                        if (
                            !values.follow_up_reason
                        ) {
                            frappe.msgprint(
                                'Please select a follow-up reason.'
                            );
                            return;
                        }

                        if (
                            !values.priority
                        ) {
                            frappe.msgprint(
                                'Please select a priority.'
                            );
                            return;
                        }

                        if (
                            !values.description
                        ) {
                            frappe.msgprint(
                                'Please enter a follow-up description.'
                            );
                            return;
                        }

                        if (
                            !values.assigned_to
                        ) {
                            frappe.msgprint(
                                'Please select who this follow-up is assigned to.'
                            );
                            return;
                        }

                        if (
                            !values.due_date
                        ) {
                            frappe.msgprint(
                                'Please select a due date.'
                            );
                            return;
                        }

                        if (
                            !values.manager_notes
                        ) {
                            frappe.msgprint(
                                'Manager Notes are required.'
                            );
                            return;
                        }

                        frappe.call({

                            method:
                                'care_management.care_management.page.manager_dashboard.manager_dashboard.create_manager_follow_up',

                            args: {

                                execution_instance:
                                    execution_instance,

                                follow_up_reason:
                                    values.follow_up_reason,

                                priority:
                                    values.priority,

                                description:
                                    values.description,

                                assigned_to:
                                    values.assigned_to,

                                due_date:
                                    values.due_date,

                                due_time:
                                    values.due_time,

                                manager_notes:
                                    values.manager_notes
                            },

                            freeze:
                                true,

                            freeze_message:
                                'Creating manager follow-up...',

                            callback:
                                function(r) {

                                    if (
                                        r.exc
                                    ) {
                                        return;
                                    }

                                    let result =
                                        r.message || {};

                                    if (
                                        result.duplicate
                                    ) {

                                        frappe.msgprint({

                                            title:
                                                'Follow-up Already Exists',

                                            message:
                                                `An active follow-up already exists: <b>${frappe.utils.escape_html(
                                                    result.follow_up.name
                                                )}</b>`,

                                            indicator:
                                                'orange'
                                        });

                                        d.hide();

                                        me.load_dashboard();

                                        return;
                                    }

                                    if (
                                        result.created
                                    ) {

                                        frappe.show_alert({

                                            message:
                                                `Follow-up ${frappe.utils.escape_html(
                                                    result.follow_up.name
                                                )} created successfully.`,

                                            indicator:
                                                'green'
                                        });

                                        d.hide();

                                        me.load_dashboard();

                                        return;
                                    }

                                    frappe.msgprint({

                                        title:
                                            'Follow-up Not Created',

                                        message:
                                            'The follow-up could not be created.',

                                        indicator:
                                            'red'
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

    display_value(
        value
    ) {

        if (
            value === null ||
            value === undefined ||
            value === ''
        ) {

            return '-';

        }

        return String(
            value
        );

    }


    // ================================================================
    // RENDER REVIEWS
    // ================================================================

    render_reviews(
        reviews
    ) {

        let me = this;


        if (
            !reviews ||
            !reviews.length
        ) {

            $('#manager-dashboard-results')
                .html(`

                    <div
                        class="manager-empty-state"
                    >

                        No execution records
                        require review for the
                        selected filters.

                    </div>

                `);

            return;
        }


        let priority_order = {

            'High': 1,

            'Medium': 2,

            'Low': 3

        };


        reviews.sort(
            function(a, b) {

                return (
                    (
                        priority_order[
                            a.review_priority
                        ] || 99
                    ) -

                    (
                        priority_order[
                            b.review_priority
                        ] || 99
                    )
                );

            }
        );


        let html = '';


        reviews.forEach(
            function(row) {

                let priority =
                    row.review_priority ||
                    'Low';


                let priority_class =
                    priority === 'High'
                        ? 'text-danger'
                        : priority === 'Medium'
                            ? 'text-warning'
                            : 'text-muted';


                let execution_instance =
                    me.safe(
                        row.execution_instance
                    );


                let support_task =
                    me.safe(
                        row.support_task
                    );


                let participant =
                    me.safe(
                        row.participant ||
                        'Participant not set'
                    );


                let task_name =
                    me.safe(
                        row.task_name ||
                        'Support Task'
                    );


                let scheduled_date =
                    me.safe(
                        row.scheduled_date
                    );


                let scheduled_time =
                    me.safe(
                        row.scheduled_time
                    );


                let status =
                    me.safe(
                        row.status
                    );


                let category =
                    me.safe(
                        row.review_category
                    );


                let exception_type =
                    me.safe(
                        row.exception_type
                    );


                let follow_up =
                    row.follow_up_required
                        ? 'Required'
                        : 'No';


                html += `

                    <div
                        class="
                            manager-review-card
                        "
                        data-execution-instance="
                            ${execution_instance}
                        "
                    >

                        <div
                            style="
                                display:flex;
                                justify-content:
                                    space-between;
                                gap:10px;
                            "
                        >

                            <div>

                                <div
                                    class="
                                        manager-review-title
                                    "
                                >
                                    ${task_name}
                                </div>

                                <div
                                    class="
                                        manager-review-meta
                                    "
                                >
                                    ${participant}
                                </div>

                            </div>


                            <div
                                class="${priority_class}"
                                style="
                                    font-weight:700;
                                    font-size:11px;
                                "
                            >

                                ${me.safe(priority)}

                            </div>

                        </div>


                        <div
                            class="
                                manager-review-grid
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

                                ${scheduled_time}
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

                                ${follow_up}
                            </div>

                        </div>


                        ${
                            exception_type
                                ? `
                                    <div
                                        style="
                                            margin-top:8px;
                                            padding:7px;
                                            background:#fff5f5;
                                            border-radius:4px;
                                            font-size:11px;
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


        $('#manager-dashboard-results')
            .html(html);


        $('.manager-review-card')
            .on(
                'click',
                function() {

                    let execution_instance =
                        $(this).attr(
                            'data-execution-instance'
                        );


                    if (
                        !execution_instance
                    ) {

                        return;
                    }


                    frappe.msgprint({

                        title:
                            'Manager Review',

                        message:
                            `
                            <p>
                                <strong>
                                    Execution Instance:
                                </strong>

                                ${frappe.utils.escape_html(
                                    execution_instance
                                )}
                            </p>

                            <p>
                                This execution record
                                is available for
                                manager review.
                            </p>
                            `,

                        indicator:
                            'blue'

                    });

                }
            );

    }


    // ================================================================
    // SAFE HTML VALUE
    // ================================================================

    safe(
        value
    ) {

        if (
            value === null ||
            value === undefined ||
            value === ''
        ) {

            return '-';

        }


        return frappe.utils.escape_html(
            String(value)
        );

    }

}