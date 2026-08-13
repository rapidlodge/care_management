frappe.ui.form.on('Daily Bowel Record Chart', {
    refresh(frm) {
        frm.events.render_bristol_chart(frm);
    },
    render_bristol_chart(frm) {
        let html = `
        <div style="padding: 10px; background-color: #f8f9fa; border: 1px solid #d1d8dd; border-radius: 8px; margin-bottom: 15px;">
            <h4 style="margin-top: 0; color: #2b2b2b; text-align: center;">Bristol Stool Chart Quick Reference</h4>
            <div style="display: flex; gap: 10px; justify-content: space-between; flex-wrap: wrap;">
                <div style="flex: 1; min-width: 220px; background: #fff3cd; border: 1px solid #ffeeba; padding: 10px; border-radius: 6px;">
                    <h5 style="color: #856404; margin-top: 0; text-align: center; border-bottom: 1px solid #ffeeba; padding-bottom: 5px;">
                        CONSTIPATION
                    </h5>
                    <p style="margin: 4px 0; font-size: 12px;"><strong>Type 1:</strong> Hard, separate pellet-like lumps (difficult to pass)</p>
                    <p style="margin: 4px 0; font-size: 12px;"><strong>Type 2:</strong> Lumpy and sausage-like</p>
                </div>
                <div style="flex: 1; min-width: 220px; background: #d4edda; border: 1px solid #c3e6cb; padding: 10px; border-radius: 6px;">
                    <h5 style="color: #155724; margin-top: 0; text-align: center; border-bottom: 1px solid #c3e6cb; padding-bottom: 5px;">
                        HEALTHY STOOL TYPES
                    </h5>
                    <p style="margin: 4px 0; font-size: 12px;"><strong>Type 3:</strong> Sausage-shaped with cracks on the surface</p>
                    <p style="margin: 4px 0; font-size: 12px;"><strong>Type 4:</strong> Sausage-shaped, smooth and soft (like a snake)</p>
                </div>
                <div style="flex: 1; min-width: 220px; background: #f8d7da; border: 1px solid #f5c6cb; padding: 10px; border-radius: 6px;">
                    <h5 style="color: #721c24; margin-top: 0; text-align: center; border-bottom: 1px solid #f5c6cb; padding-bottom: 5px;">
                        DIARRHEA
                    </h5>
                    <p style="margin: 4px 0; font-size: 12px;"><strong>Type 5:</strong> Soft blobs with clear edges (passes easily)</p>
                    <p style="margin: 4px 0; font-size: 12px;"><strong>Type 6:</strong> Fluffy pieces with ragged edges, mushy</p>
                    <p style="margin: 4px 0; font-size: 12px;"><strong>Type 7:</strong> Watery, entirely liquid with no solid pieces</p>
                </div>
            </div>
        </div>
        `;
        frm.get_field('bristol_chart_html').$wrapper.html(html);
    }
});
