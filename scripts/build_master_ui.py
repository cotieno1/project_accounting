"""Write master-registry.js and patch dashboard - run: python scripts/build_master_ui.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

JS = r'''/**
 * Pioneer Master Data Registry
 */
const MasterRegistry = (function () {
    const ENTITY_CONFIG = {
        user: { title: "User Accounts", icon: "User", createUrl: "/users/create/",
            fields: [
                { name: "staff_no", label: "Staff Number", type: "text", required: true },
                { name: "username", label: "Login Username", type: "text", required: true, editReadonly: true },
                { name: "first_name", label: "First Name", type: "text", required: true },
                { name: "last_name", label: "Last Name", type: "text", required: true },
                { name: "designation", label: "Designation", type: "text", required: true },
                { name: "phone", label: "Phone", type: "text" },
                { name: "email", label: "Email", type: "email", required: true },
                { name: "contact_address", label: "Address", type: "textarea" },
                { name: "access_level_id", label: "Role / Category", type: "role_select" },
            ]},
        role: { title: "User Categories", icon: "Role", createUrl: "/roles/create/",
            fields: [{ name: "description", label: "Category Name", type: "text", required: true }] },
        bank: { title: "Bank Accounts", icon: "Bank", createUrl: "/bank/create/",
            fields: [
                { name: "bank_account_id", label: "Bank ID", type: "text", required: true, pk: true },
                { name: "account_number", label: "Account Number", type: "text", required: true },
                { name: "description", label: "Bank Name", type: "text", required: true },
                { name: "phone", label: "Phone", type: "text" },
                { name: "email", label: "Email", type: "email" },
                { name: "contact_address", label: "Address", type: "textarea" },
            ]},
        supplier: { title: "Supplier Accounts", icon: "Supplier", createUrl: "/supplier/create/",
            fields: [
                { name: "supplier_id", label: "Supplier ID", type: "text", required: true, pk: true },
                { name: "description", label: "Company Name", type: "text", required: true },
                { name: "bank_account_number", label: "Bank Account No", type: "text" },
                { name: "phone", label: "Phone", type: "text" },
                { name: "email", label: "Email", type: "email" },
                { name: "contact_address", label: "Address", type: "textarea" },
            ]},
        gl: { title: "GL Accounts", icon: "GL", createUrl: "/gl/create/",
            fields: [
                { name: "gl_account_id", label: "GL Code", type: "text", required: true, pk: true },
                { name: "description", label: "Account Name", type: "text", required: true },
                { name: "debit_credit", label: "Debit / Credit", type: "select", options: [["DR","Debit (DR)"],["CR","Credit (CR)"]] },
                { name: "analysis_category", label: "Analysis Category", type: "analysis_select" },
                { name: "currency", label: "Currency", type: "text", default: "US$" },
                { name: "amount", label: "Opening Amount", type: "number", step: "0.01" },
            ]},
        analysis: { title: "GL Analysis Codes", icon: "Analysis", createUrl: "/analysis/create/",
            fields: [
                { name: "category_id", label: "Analysis Code", type: "text", required: true, pk: true },
                { name: "description", label: "Description", type: "text", required: true },
            ]},
        task: { title: "Project Tasks", icon: "Task", createUrl: "/task/create/",
            fields: [
                { name: "project_id", label: "Task ID", type: "text", required: true, pk: true },
                { name: "description", label: "Description", type: "text", required: true },
            ]},
        build: { title: "Build Categories", icon: "Build", createUrl: "/build/create/",
            fields: [
                { name: "build_cat_id", label: "Category ID", type: "text", required: true },
                { name: "description", label: "Description", type: "text", required: true },
            ]},
        product: { title: "Product Items", icon: "Product", createUrl: "/product/create/",
            fields: [
                { name: "product_id", label: "Product Code", type: "text", required: true, pk: true },
                { name: "description", label: "Description", type: "text", required: true },
                { name: "unit_of_measure", label: "UOM", type: "text", default: "EA" },
                { name: "stock_quantity", label: "Stock Qty", type: "number", default: "0" },
            ]},
    };

    let activeEntity = null;
    let listCache = [];
    let lastColumns = [];
    let roleOptions = [];
    let analysisOptions = [];

    function csrfToken() {
        const el = document.querySelector("[name=csrfmiddlewaretoken]");
        return el ? el.value : "";
    }

    function toast(msg, type) {
        const box = document.getElementById("masterToast");
        if (!box) return;
        box.textContent = msg;
        box.className = "master-toast master-toast-" + (type || "success") + " master-toast-show";
        clearTimeout(box._t);
        box._t = setTimeout(function () { box.classList.remove("master-toast-show"); }, 4000);
    }

    function esc(s) {
        return String(s == null ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }

    function loadBootstrap() {
        const r = document.getElementById("role-options-data");
        const a = document.getElementById("analysis-options-data");
        if (r) roleOptions = JSON.parse(r.textContent || "[]");
        if (a) analysisOptions = JSON.parse(a.textContent || "[]");
    }

    function openList(entityType) {
        activeEntity = entityType;
        const cfg = ENTITY_CONFIG[entityType];
        if (!cfg) return;
        document.getElementById("setupDropdown").classList.remove("is-open");
        document.getElementById("masterListTitle").textContent = cfg.title;
        document.getElementById("masterListSubtitle").textContent = "List, view, edit and delete master records";
        document.getElementById("masterSearch").value = "";
        document.getElementById("masterListPanel").classList.add("is-open");
        document.getElementById("masterFormPanel").classList.remove("is-open");
        refreshList();
    }

    function closePanels() {
        document.getElementById("masterListPanel").classList.remove("is-open");
        document.getElementById("masterFormPanel").classList.remove("is-open");
    }

    function refreshList() {
        const tbody = document.getElementById("masterTableBody");
        tbody.innerHTML = '<tr><td colspan="12" class="master-empty">Loading...</td></tr>';
        fetch("/api/list/" + activeEntity + "/").then(function (r) { return r.json(); }).then(function (res) {
            if (res.status !== "success") throw new Error(res.message || "Failed");
            listCache = res.data || [];
            lastColumns = res.columns || [];
            const thead = document.getElementById("masterTableHead");
            thead.innerHTML = "<tr>" + lastColumns.map(function (c) { return "<th>" + esc(c[1]) + "</th>"; }).join("") +
                '<th class="master-actions-col">Actions</th></tr>';
            renderRows();
        }).catch(function (e) {
            tbody.innerHTML = '<tr><td colspan="12" class="master-empty master-error">' + esc(e.message) + "</td></tr>";
        });
    }

    function renderRows() {
        const tbody = document.getElementById("masterTableBody");
        const q = (document.getElementById("masterSearch").value || "").trim().toLowerCase();
        const filtered = listCache.filter(function (row) {
            if (!q) return true;
            return Object.keys(row).some(function (k) { return String(row[k]).toLowerCase().indexOf(q) >= 0; });
        });
        if (!filtered.length) {
            tbody.innerHTML = '<tr><td colspan="12" class="master-empty">No records found.</td></tr>';
            document.getElementById("masterRecordCount").textContent = "0 records";
            return;
        }
        tbody.innerHTML = filtered.map(function (row) {
            const pk = row._pk;
            const cells = lastColumns.map(function (c) { return "<td>" + esc(row[c[0]]) + "</td>"; }).join("");
            return "<tr>" + cells + '<td class="master-actions-col">' +
                '<button type="button" class="master-btn master-btn-ghost" data-act="view" data-pk="' + esc(pk) + '">View</button> ' +
                '<button type="button" class="master-btn master-btn-primary" data-act="edit" data-pk="' + esc(pk) + '">Edit</button> ' +
                '<button type="button" class="master-btn master-btn-danger" data-act="del" data-pk="' + esc(pk) + '">Delete</button></td></tr>';
        }).join("");
        document.getElementById("masterRecordCount").textContent = filtered.length + " of " + listCache.length + " records";
        tbody.querySelectorAll("[data-act]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                const pk = btn.getAttribute("data-pk");
                const act = btn.getAttribute("data-act");
                if (act === "view") viewRecord(pk);
                else if (act === "edit") editRecord(pk);
                else if (act === "del") deleteRecord(pk);
            });
        });
    }

    function fieldHtml(f, mode) {
        const id = "mf_" + f.name;
        const req = f.required ? " required" : "";
        if (f.type === "textarea") return '<div class="master-field"><label for="' + id + '">' + f.label + '</label><textarea class="master-input" name="' + f.name + '" id="' + id + '" rows="3"' + req + '></textarea></div>';
        if (f.type === "select") {
            var opts = (f.options || []).map(function (o) { return '<option value="' + o[0] + '">' + o[1] + "</option>"; }).join("");
            return '<div class="master-field"><label for="' + id + '">' + f.label + '</label><select class="master-input" name="' + f.name + '" id="' + id + '"' + req + '>' + opts + "</select></div>";
        }
        if (f.type === "role_select") {
            var ro = '<option value="">Select role</option>' + roleOptions.map(function (r) { return '<option value="' + r.id + '">' + esc(r.description) + "</option>"; }).join("");
            return '<div class="master-field"><label for="' + id + '">' + f.label + '</label><select class="master-input" name="' + f.name + '" id="' + id + '">' + ro + "</select></div>";
        }
        if (f.type === "analysis_select") {
            var ao = '<option value="">Select analysis</option>' + analysisOptions.map(function (r) { return '<option value="' + esc(r.category_id) + '">' + esc(r.description) + "</option>"; }).join("");
            return '<div class="master-field"><label for="' + id + '">' + f.label + '</label><select class="master-input" name="' + f.name + '" id="' + id + '">' + ao + "</select></div>";
        }
        var roAttr = (f.pk && mode === "edit") || (f.editReadonly && mode === "edit") ? ' readonly class="master-input is-readonly"' : ' class="master-input"';
        var def = f.default && mode === "create" ? ' value="' + f.default + '"' : "";
        return '<div class="master-field"><label for="' + id + '">' + f.label + (f.required ? " *" : "") + '</label><input type="' + (f.type || "text") + '" name="' + f.name + '" id="' + id + '"' + roAttr + def + req + "></div>";
    }

    function openForm(mode, pk) {
        const cfg = ENTITY_CONFIG[activeEntity];
        document.getElementById("masterFormTitle").textContent = (mode === "edit" ? "Edit " : mode === "view" ? "View " : "Add ") + cfg.title;
        document.getElementById("masterFormMode").value = mode === "view" ? "edit" : mode;
        document.getElementById("masterFormPk").value = pk || "";
        document.getElementById("masterFormFields").innerHTML = cfg.fields.map(function (f) { return fieldHtml(f, mode); }).join("");
        document.getElementById("masterFormPanel").classList.add("is-open");
        document.getElementById("masterListPanel").classList.remove("is-open");
        document.getElementById("masterFormSave").style.display = mode === "view" ? "none" : "";
        document.querySelectorAll("#masterEntityForm input, #masterEntityForm select, #masterEntityForm textarea").forEach(function (el) { el.disabled = mode === "view"; });
        if ((mode === "edit" || mode === "view") && pk) {
            fetch("/api/detail/" + activeEntity + "/" + encodeURIComponent(pk) + "/").then(function (r) { return r.json(); }).then(function (res) {
                Object.keys(res.data || {}).forEach(function (k) {
                    var el = document.querySelector('#masterEntityForm [name="' + k + '"]');
                    if (el) el.value = res.data[k] != null ? res.data[k] : "";
                });
            });
        }
    }

    function openAdd() { openForm("create", ""); }
    function editRecord(pk) { openForm("edit", pk); }
    function viewRecord(pk) { openForm("view", pk); }

    function backToList() {
        document.getElementById("masterFormPanel").classList.remove("is-open");
        document.getElementById("masterListPanel").classList.add("is-open");
        document.querySelectorAll("#masterEntityForm input, #masterEntityForm select, #masterEntityForm textarea").forEach(function (el) { el.disabled = false; });
        refreshList();
    }

    function saveForm(e) {
        e.preventDefault();
        const cfg = ENTITY_CONFIG[activeEntity];
        const fd = new FormData(document.getElementById("masterEntityForm"));
        fd.append("mode", document.getElementById("masterFormMode").value);
        const pk = document.getElementById("masterFormPk").value;
        if (pk) fd.append("original_id", pk);
        fetch(cfg.createUrl, { method: "POST", body: fd, headers: { "X-CSRFToken": csrfToken() } })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (res.status === "success") { toast(res.message); backToList(); }
                else toast(res.message || "Save failed", "error");
            }).catch(function () { toast("Save failed", "error"); });
    }

    function deleteRecord(pk) {
        if (!confirm("Delete this record permanently?")) return;
        fetch("/api/delete/" + activeEntity + "/" + encodeURIComponent(pk) + "/", { method: "DELETE" })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (res.status === "success") { toast(res.message); refreshList(); }
                else toast(res.message || "Delete failed", "error");
            });
    }

    function toggleSetupMenu() {
        document.getElementById("setupDropdown").classList.toggle("is-open");
    }

    document.addEventListener("DOMContentLoaded", function () {
        loadBootstrap();
        document.getElementById("masterSearch").addEventListener("input", renderRows);
        document.getElementById("masterEntityForm").addEventListener("submit", saveForm);
        document.addEventListener("click", function (e) {
            var menu = document.getElementById("setupDropdown");
            var btn = document.getElementById("setupMenuBtn");
            if (menu && btn && !menu.contains(e.target) && !btn.contains(e.target)) menu.classList.remove("is-open");
        });
        document.addEventListener("keydown", function (e) { if (e.key === "Escape") closePanels(); });
    });

    return { openList: openList, openAdd: function (t) { openList(t); openAdd(); }, editRecord: editRecord, viewRecord: viewRecord, deleteRecord: deleteRecord, backToList: backToList, closePanels: closePanels, toggleSetupMenu: toggleSetupMenu };
})();
'''

(ROOT / "static/js/master-registry.js").write_text(JS, encoding="utf-8", newline="\n")
print("Wrote master-registry.js")
