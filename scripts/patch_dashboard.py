from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
dash = ROOT / "templates" / "dashboard.html"
text = dash.read_text(encoding="utf-8", errors="replace")
marker = "<!-- legacy modal placeholder removed -->"
start = text.find(marker)
if start < 0:
    raise SystemExit("marker not found")
body_end = text.rfind("</body>")
new_tail = '''<script>
var activeEntityType = null;
const MasterRegistry = (function () {
    const CFG = {
        user: { title: "User Accounts", url: "/users/create/", fields: [
            ["staff_no","Staff Number","text",1],["username","Login Username","text",1,1],
            ["first_name","First Name","text",1],["last_name","Last Name","text",1],
            ["designation","Designation","text",1],["phone","Phone","text",0],
            ["email","Email","email",1],["contact_address","Address","area",0],["access_level_id","Role","role",0]] },
        role: { title: "User Categories", url: "/roles/create/", fields: [["description","Category Name","text",1]] },
        bank: { title: "Bank Accounts", url: "/bank/create/", fields: [
            ["bank_account_id","Bank ID","text",1,1],["account_number","Account Number","text",1],
            ["description","Bank Name","text",1],["phone","Phone","text",0],["email","Email","email",0],["contact_address","Address","area",0]] },
        supplier: { title: "Supplier Accounts", url: "/supplier/create/", fields: [
            ["supplier_id","Supplier ID","text",1,1],["description","Company Name","text",1],
            ["bank_account_number","Bank A/C","text",0],["phone","Phone","text",0],["email","Email","email",0],["contact_address","Address","area",0]] },
        gl: { title: "GL Accounts", url: "/gl/create/", fields: [
            ["gl_account_id","GL Code","text",1,1],["description","Account Name","text",1],
            ["debit_credit","Dr/Cr","drcr",0],["analysis_category","Analysis","analysis",0],
            ["currency","Currency","text",0],["amount","Amount","number",0]] },
        analysis: { title: "GL Analysis Codes", url: "/analysis/create/", fields: [
            ["category_id","Code","text",1,1],["description","Description","text",1]] },
        task: { title: "Project Tasks", url: "/task/create/", fields: [
            ["project_id","Task ID","text",1,1],["description","Description","text",1]] },
        build: { title: "Build Categories", url: "/build/create/", fields: [
            ["build_cat_id","Category ID","text",1],["description","Description","text",1]] },
        product: { title: "Product Items", url: "/product/create/", fields: [
            ["product_id","Product Code","text",1,1],["description","Description","text",1],
            ["unit_of_measure","UOM","text",0],["stock_quantity","Stock","number",0]] },
    };
    let rows = [], cols = [], roles = [], analysis = [];
    function csrf() { const e = document.querySelector("[name=csrfmiddlewaretoken]"); return e ? e.value : ""; }
    function toast(m, t) { const b = document.getElementById("masterToast"); b.textContent = m; b.className = "master-toast master-toast-" + (t||"success") + " master-toast-show"; clearTimeout(b._t); b._t = setTimeout(() => b.classList.remove("master-toast-show"), 3500); }
    function esc(s) { return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;"); }
    function loadOpts() {
        const r = document.getElementById("role-options-data"); const a = document.getElementById("analysis-options-data");
        if (r) roles = JSON.parse(r.textContent||"[]"); if (a) analysis = JSON.parse(a.textContent||"[]");
    }
    function openList(t) {
        activeEntityType = t; const c = CFG[t];
        document.getElementById("setupDropdown").classList.remove("is-open");
        document.getElementById("masterListTitle").textContent = c.title;
        document.getElementById("masterSearch").value = "";
        document.getElementById("masterListPanel").classList.add("is-open");
        document.getElementById("masterFormPanel").classList.remove("is-open");
        refresh();
    }
    function closePanels() { document.getElementById("masterListPanel").classList.remove("is-open"); document.getElementById("masterFormPanel").classList.remove("is-open"); }
    function refresh() {
        const body = document.getElementById("masterTableBody");
        body.innerHTML = '<tr><td colspan="12" class="master-empty">Loading...</td></tr>';
        fetch("/api/list/" + activeEntityType + "/").then(r=>r.json()).then(res => {
            if (res.status !== "success") throw new Error(res.message||"Failed");
            rows = res.data||[]; cols = res.columns||[]; render();
        }).catch(e => { body.innerHTML = '<tr><td colspan="12" class="master-empty master-error">'+esc(e.message)+'</td></tr>'; });
    }
    function render() {
        const q = (document.getElementById("masterSearch").value||"").trim().toLowerCase();
        const filtered = rows.filter(r => !q || Object.values(r).some(v => String(v).toLowerCase().includes(q)));
        document.getElementById("masterTableHead").innerHTML = "<tr>" + cols.map(c=>"<th>"+esc(c[1])+"</th>").join("") + '<th class="master-actions-col">Actions</th></tr>';
        const body = document.getElementById("masterTableBody");
        if (!filtered.length) { body.innerHTML = '<tr><td colspan="12" class="master-empty">No records</td></tr>'; document.getElementById("masterRecordCount").textContent="0 records"; return; }
        body.innerHTML = filtered.map(r => {
            const pk = r._pk;
            const cells = cols.map(c => "<td>"+esc(r[c[0]])+"</td>").join("");
            return "<tr>"+cells+'<td class="master-actions-col"><button type="button" class="master-btn master-btn-ghost" onclick="MasterRegistry.viewRecord(\\''+pk+'\\')">View</button><button type="button" class="master-btn master-btn-primary" onclick="MasterRegistry.editRecord(\\''+pk+'\\')">Edit</button><button type="button" class="master-btn master-btn-danger" onclick="MasterRegistry.deleteRecord(\\''+pk+'\\')">Delete</button></td></tr>';
        }).join("");
        document.getElementById("masterRecordCount").textContent = filtered.length + " of " + rows.length + " records";
    }
    function fieldHtml(f, mode) {
        const n=f[0], label=f[1], typ=f[2], req=f[3], pk=f[4];
        const id="mf_"+n, rq=req?" required":"";
        if (typ==="area") return '<div class="master-field"><label>'+label+'</label><textarea class="master-input" name="'+n+'" id="'+id+'" rows="3"'+rq+'></textarea></div>';
        if (typ==="drcr") return '<div class="master-field"><label>'+label+'</label><select class="master-input" name="'+n+'" id="'+id+'"><option value="DR">Debit (DR)</option><option value="CR">Credit (CR)</option></select></div>';
        if (typ==="role") return '<div class="master-field"><label>'+label+'</label><select class="master-input" name="'+n+'" id="'+id+'"><option value="">Select role</option>'+roles.map(r=>'<option value="'+r.id+'">'+esc(r.description)+'</option>').join("")+'</select></div>';
        if (typ==="analysis") return '<div class="master-field"><label>'+label+'</label><select class="master-input" name="'+n+'" id="'+id+'"><option value="">Select analysis</option>'+analysis.map(r=>'<option value="'+esc(r.category_id)+'">'+esc(r.description)+'</option>').join("")+'</select></div>';
        const ro = (pk && mode==="edit") ? ' readonly class="master-input is-readonly"' : ' class="master-input"';
        return '<div class="master-field"><label>'+label+(req?" *":"")+'</label><input type="'+(typ==="number"?"number":"text")+'" name="'+n+'" id="'+id+'"'+ro+rq+'></div>';
    }
    function openForm(mode, pk) {
        const c = CFG[activeEntityType];
        document.getElementById("masterFormTitle").textContent = (mode==="edit"?"Edit ":mode==="view"?"View ":"Add ") + c.title;
        document.getElementById("masterFormMode").value = mode==="view"?"edit":mode;
        document.getElementById("masterFormPk").value = pk||"";
        document.getElementById("masterFormFields").innerHTML = c.fields.map(f => fieldHtml(f, mode)).join("");
        document.getElementById("masterFormPanel").classList.add("is-open");
        document.getElementById("masterListPanel").classList.remove("is-open");
        document.getElementById("masterFormSave").style.display = mode==="view"?"none":"";
        document.querySelectorAll("#masterEntityForm input, #masterEntityForm select, #masterEntityForm textarea").forEach(el => { el.disabled = mode==="view"; });
        if ((mode==="edit"||mode==="view") && pk) {
            fetch("/api/detail/"+activeEntityType+"/"+encodeURIComponent(pk)+"/").then(r=>r.json()).then(res => {
                Object.entries(res.data||{}).forEach(([k,v]) => { const el=document.querySelector('#masterEntityForm [name="'+k+'"]'); if(el) el.value=v??""; });
            });
        }
    }
    function openAdd(t) { if (t) openList(t); openForm("create",""); }
    function editRecord(pk) { openForm("edit", pk); }
    function viewRecord(pk) { openForm("view", pk); }
    function backToList() { document.getElementById("masterFormPanel").classList.remove("is-open"); document.getElementById("masterListPanel").classList.add("is-open"); document.querySelectorAll("#masterEntityForm input, #masterEntityForm select, #masterEntityForm textarea").forEach(el=>el.disabled=false); refresh(); }
    function saveForm(e) {
        e.preventDefault(); const c = CFG[activeEntityType]; const fd = new FormData(document.getElementById("masterEntityForm"));
        fd.append("mode", document.getElementById("masterFormMode").value);
        const pk = document.getElementById("masterFormPk").value; if (pk) fd.append("original_id", pk);
        fetch(c.url, { method:"POST", body:fd, headers:{"X-CSRFToken":csrf()} }).then(r=>r.json()).then(res => {
            if (res.status==="success") { toast(res.message); backToList(); } else toast(res.message||"Save failed","error");
        }).catch(()=>toast("Save failed","error"));
    }
    function deleteRecord(pk) {
        if (!confirm("Delete this record permanently?")) return;
        fetch("/api/delete/"+activeEntityType+"/"+encodeURIComponent(pk)+"/", {method:"DELETE"}).then(r=>r.json()).then(res => {
            if (res.status==="success") { toast(res.message); refresh(); } else toast(res.message||"Delete failed","error");
        });
    }
    function toggleSetupMenu() { document.getElementById("setupDropdown").classList.toggle("is-open"); }
    document.addEventListener("DOMContentLoaded", () => {
        loadOpts();
        document.getElementById("masterSearch").addEventListener("input", render);
        document.getElementById("masterEntityForm").addEventListener("submit", saveForm);
        document.getElementById("masterListAddBtn").addEventListener("click", () => openAdd(activeEntityType));
        document.addEventListener("click", e => { const m=document.getElementById("setupDropdown"), b=document.getElementById("setupMenuBtn"); if(m&&b&&!m.contains(e.target)&&!b.contains(e.target)) m.classList.remove("is-open"); });
        document.addEventListener("keydown", e => { if (e.key==="Escape") closePanels(); });
    });
    return { openList, openAdd, editRecord, viewRecord, deleteRecord, backToList, closePanels, toggleSetupMenu };
})();
</script>

</body>
</html>
'''
dash.write_text(text[:start] + new_tail, encoding="utf-8", newline="\n")
print("patched dashboard.html")
