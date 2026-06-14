(function () {
    const adhocRosData = JSON.parse(
        document.getElementById("gm-adhoc-ros-data")?.textContent || "[]"
    );
    const officerPvsData = JSON.parse(
        document.getElementById("gm-officer-pvs-data")?.textContent || "[]"
    );
    const gmTaskCaps = JSON.parse(
        document.getElementById("gm-task-caps")?.textContent || "{}"
    );
    let activeAdhocRo = null;
    let settleAdvance = 0;

    window.openAdhocRoModal = function () {
        if (gmTaskCaps.enable_adhoc_ro === false) return;
        renderAdhocRoList();
        hideAdhocRoDetail();
        document.getElementById("adhocRoModal").style.display = "flex";
    };
    window.closeAdhocRoModal = function () {
        document.getElementById("adhocRoModal").style.display = "none";
    };
    window.openOfficerPvPeriodModal = function () {
        if (gmTaskCaps.enable_officer_pv === false) return;
        document.getElementById("officerPvPeriodModal").style.display = "flex";
    };
    window.closeOfficerPvPeriodModal = function () {
        document.getElementById("officerPvPeriodModal").style.display = "none";
    };
    window.hideAdhocRoDetail = function () {
        document.getElementById("adhoc-ro-detail-pane").style.display = "none";
        document.getElementById("adhoc-ro-list-pane").style.display = "block";
        activeAdhocRo = null;
    };

    function adhocPurchaseBadge(status) {
        const labels = { FULL: "Full", PARTIAL: "Partial", NONE: "Unpaid" };
        const cls =
            status === "FULL"
                ? "goods-status-full"
                : status === "PARTIAL"
                  ? "goods-status-partial"
                  : "goods-status-none";
        return `<span class="goods-status-badge ${cls}">${labels[status] || status}</span>`;
    }

    function fmtAdhocQty(n) {
        const v = parseFloat(n);
        if (Number.isNaN(v)) return "0";
        return String(Math.round(v));
    }

    function renderAdhocRoList() {
        const tbody = document.getElementById("adhoc-ro-list-tbody");
        const empty = document.getElementById("adhoc-ro-list-empty");
        if (!tbody) return;
        tbody.innerHTML = "";
        if (!adhocRosData.length) {
            if (empty) empty.style.display = "block";
            return;
        }
        if (empty) empty.style.display = "none";
        adhocRosData.forEach((ro) => {
            const tr = document.createElement("tr");
            tr.style.cursor = "pointer";
            tr.onclick = () => showAdhocRoDetail(ro.id);
            const vc = (ro.vouchers || []).length;
            tr.innerHTML =
                `<td style="font-family:monospace;font-weight:700;">${ro.ref}</td>` +
                `<td>${ro.status_label}</td>` +
                `<td>${adhocPurchaseBadge(ro.purchase_status || "NONE")}</td>` +
                `<td>${ro.date}</td>` +
                `<td class="num">${ro.amount}</td><td>${vc || "—"}</td>` +
                `<td><button type="button" class="registry-link" style="background:none;border:none;cursor:pointer;" ` +
                `onclick="event.stopPropagation();showAdhocRoDetail('${ro.id}')">Open</button></td>`;
            tbody.appendChild(tr);
        });
    }

    window.showAdhocRoDetail = function (roId) {
        const ro = adhocRosData.find((r) => r.id === roId);
        if (!ro) return;
        activeAdhocRo = ro;
        document.getElementById("adhoc-ro-list-pane").style.display = "none";
        document.getElementById("adhoc-ro-detail-pane").style.display = "block";
        document.getElementById("adhoc-ro-detail-title").textContent = ro.ref;
        const hasBuyable = (ro.items || []).some(
            (i) => (parseFloat(i.qty_remaining_raw) || 0) > 0
        );
        document.getElementById("adhoc-ro-detail-meta").textContent = ro.can_purchase
            ? "Select lines (partial or full qty), enter officer name, raise payment voucher against this RO."
            : hasBuyable
              ? "Submit this RO before raising payment vouchers."
              : "All RO lines fully paid via payment vouchers.";
        const outstandingCount = (ro.items || []).filter(
            (i) => (parseFloat(i.qty_remaining_raw) || 0) > 0
        ).length;
        const summaryEl = document.getElementById("adhoc-ro-detail-summary");
        if (summaryEl) {
            summaryEl.innerHTML =
                `${ro.items.length} line item(s) · ${adhocPurchaseBadge(ro.purchase_status || "NONE")}` +
                ` · ${outstandingCount} with outstanding balance · ${(ro.vouchers || []).length} payment voucher(s) raised`;
        }
        const tbody = document.getElementById("adhoc-ro-detail-items");
        tbody.innerHTML = "";
        (ro.items || []).forEach((item) => {
            const rem = parseFloat(item.qty_remaining_raw) || 0;
            const canBuy = ro.can_purchase && rem > 0;
            const outCls = rem > 0 ? "goods-outstanding" : "goods-outstanding-zero";
            const purchaseHtml = (item.purchases || []).length
                ? item.purchases
                      .map(
                          (p) =>
                              `<div class="goods-delivery-log">${p.date} · <a href="${p.print_url}" class="registry-link" target="_blank">${p.voucher_no}</a> · ${p.officer} · <strong>${fmtAdhocQty(p.qty)}</strong> ${item.uom} · ${fmtMoney(p.amount)}</div>`
                      )
                      .join("")
                : '<span style="color:var(--muted);font-size:11px;">—</span>';
            const tr = document.createElement("tr");
            tr.dataset.itemId = item.id;
            tr.dataset.unitPrice = item.unit_price_raw;
            tr.dataset.remaining = rem;
            tr.innerHTML =
                `<td style="text-align:center;font-weight:700;color:var(--warning);">${item.index}</td>` +
                `<td>${canBuy ? '<input type="checkbox" class="adhoc-ro-check" onchange="toggleAdhocRoRow(this)">' : "—"}</td>` +
                `<td>${item.description} ${item.line_status ? adhocPurchaseBadge(item.line_status) : ""}</td>` +
                `<td>${item.uom}</td>` +
                `<td class="num">${item.qty_ordered}</td>` +
                `<td class="num">${item.qty_purchased}</td>` +
                `<td class="num ${outCls}">${item.qty_remaining}</td>` +
                `<td class="num">${item.unit_price}</td>` +
                `<td class="num">${canBuy ? `<input type="number" class="form-input adhoc-ro-qty" min="0" max="${rem}" step="1" style="width:80px;padding:4px;" oninput="onAdhocRoQtyInput(this)">` : "—"}</td>` +
                `<td>${purchaseHtml}</td>`;
            tbody.appendChild(tr);
        });
        document.getElementById("adhoc-ro-selection-bar").style.display = ro.can_purchase
            ? "flex"
            : "none";
        const hint = document.getElementById("adhoc-ro-blocked-hint");
        hint.style.display = !ro.can_purchase && hasBuyable ? "block" : "none";
        if (hint.style.display === "block") {
            hint.textContent = "RO must be submitted before payment vouchers can be raised.";
        }
        document.getElementById("adhoc-ro-officer-name").value = "";
        document.getElementById("adhoc-ro-voucher-btn").onclick = () =>
            openOfficerPaymentVoucherModalFromRo();
        updateAdhocRoSelectionSummary();
    };

    window.toggleAdhocRoRow = function (cb) {
        const tr = cb.closest("tr");
        const qty = tr.querySelector(".adhoc-ro-qty");
        if (!cb.checked && qty) qty.value = "";
        updateAdhocRoSelectionSummary();
    };
    window.onAdhocRoQtyInput = function (input) {
        const tr = input.closest("tr");
        const cb = tr.querySelector(".adhoc-ro-check");
        let v = Math.round(parseFloat(input.value) || 0);
        if (input.value !== "" && v !== parseFloat(input.value)) {
            input.value = v > 0 ? v : "";
        }
        if (cb && v > 0) cb.checked = true;
        const max = Math.round(parseFloat(tr.dataset.remaining) || 0);
        if (v > max) input.value = max;
        updateAdhocRoSelectionSummary();
    };

    function collectAdhocRoLines() {
        const lines = [];
        let total = 0;
        document.querySelectorAll("#adhoc-ro-detail-items tr").forEach((tr, idx) => {
            const cb = tr.querySelector(".adhoc-ro-check");
            if (!cb?.checked) return;
            const qty = Math.round(parseFloat(tr.querySelector(".adhoc-ro-qty")?.value) || 0);
            if (qty <= 0) return;
            const unit = parseFloat(tr.dataset.unitPrice) || 0;
            const lineTotal = qty * unit;
            lines.push({
                item_id: tr.dataset.itemId,
                qty_purchase: qty,
                line_no: parseInt(tr.querySelector("td")?.textContent, 10) || lines.length + 1,
                line_total: lineTotal.toFixed(2),
            });
            total += lineTotal;
        });
        return { lines, total };
    }

    function updateAdhocRoSelectionSummary() {
        const { lines, total } = collectAdhocRoLines();
        const countEl = document.getElementById("adhoc-ro-selected-count");
        const totalEl = document.getElementById("adhoc-ro-selected-total");
        if (countEl) countEl.textContent = String(lines.length);
        if (totalEl) totalEl.textContent = fmtMoney(total);
    }
    window.updateAdhocRoSelectionSummary = updateAdhocRoSelectionSummary;

    function openOfficerPaymentVoucherModalFromRo() {
        if (!activeAdhocRo) return;
        const { lines, total } = collectAdhocRoLines();
        if (!lines.length) {
            alert("Tick at least one line and enter PV quantity (partial or full).");
            return;
        }
        const officer = (document.getElementById("adhoc-ro-officer-name").value || "").trim();
        if (!officer) {
            alert("Enter the officer name (e.g. James).");
            return;
        }
        document.getElementById("opv-mpo-id").value = activeAdhocRo.id;
        document.getElementById("opv-modal-ro-tag").textContent = activeAdhocRo.ref;
        document.getElementById("opv-lines-json").value = JSON.stringify(lines);
        document.getElementById("opv-lines-summary").innerHTML = lines
            .map((l) => {
                const item = activeAdhocRo.items.find((i) => i.id === l.item_id);
                return `<div>${item?.description || "Item"} × ${Math.round(parseFloat(l.qty_purchase) || 0)} @ ${fmtMoney(item?.unit_price || 0)} = ${fmtMoney(l.line_total)}</div>`;
            })
            .join("");
        document.getElementById("opv-amount-display").textContent = total.toFixed(2);
        document.getElementById("opv-officer-name").value = officer;
        document.getElementById("opv-mpesa-ref").value = "";
        document.getElementById("opv-gm-name").value = "";
        document.getElementById("opv-prepared-by").value = "";
        document.getElementById("opv-notes").value = "";
        document.getElementById("opv-payment-method").value = "CASH";
        toggleOpvMethodFields();
        document.getElementById("officerPaymentVoucherModal").style.display = "flex";
    }

    window.closeOfficerPaymentVoucherModal = function () {
        document.getElementById("officerPaymentVoucherModal").style.display = "none";
    };
    window.toggleOpvMethodFields = function () {
        const m = document.getElementById("opv-payment-method").value;
        document.getElementById("opv-mpesa-fields").style.display =
            m === "MPESA" ? "block" : "none";
        const ref = document.getElementById("opv-mpesa-ref");
        if (ref) ref.required = m === "MPESA";
    };

    window.openOfficerPvSettleModal = function (pvId) {
        const pv = officerPvsData.find((x) => x.id === parseInt(pvId, 10));
        if (!pv) return;
        settleAdvance = parseFloat(pv.amount) || 0;
        document.getElementById("opv-settle-id").value = pv.id;
        document.getElementById("opv-settle-intro").innerHTML =
            `<strong>${pv.voucher_no}</strong> · Officer <strong>${pv.officer_name}</strong> · Advance ${fmtMoney(pv.amount)}.`;
        document.getElementById("opv-settle-spent").value = "";
        document.getElementById("opv-settle-change").value = "0";
        document.getElementById("opv-settle-receipt").value = "";
        document.getElementById("opv-settle-by").value = "";
        document.getElementById("officerPvSettleModal").style.display = "flex";
    };
    window.closeOfficerPvSettleModal = function () {
        document.getElementById("officerPvSettleModal").style.display = "none";
    };
    window.updateOpvSettleChange = function () {
        const spent = parseFloat(document.getElementById("opv-settle-spent").value) || 0;
        document.getElementById("opv-settle-change").value = Math.max(
            0,
            settleAdvance - spent
        ).toFixed(2);
    };

    ["adhocRoModal", "officerPvPeriodModal", "officerPaymentVoucherModal", "officerPvSettleModal"].forEach(
        (id) => {
            document.getElementById(id)?.addEventListener("click", (e) => {
                if (e.target.id !== id) return;
                if (id === "adhocRoModal") closeAdhocRoModal();
                if (id === "officerPvPeriodModal") closeOfficerPvPeriodModal();
                if (id === "officerPaymentVoucherModal") closeOfficerPaymentVoucherModal();
                if (id === "officerPvSettleModal") closeOfficerPvSettleModal();
            });
        }
    );
})();
