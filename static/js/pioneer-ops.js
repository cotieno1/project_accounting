/**
 * Pioneer Operations Engine v2.0 - UNIFIED
 * Handles Dynamic CRUD, Registry Rendering, and Modal Orchestration
 */

const PioneerController = {
    // 1. DATA ENTRY: Opens the entry form with the correct schema
    openEntryForm: function(entityType) {
        const modal = document.getElementById('pioneerModal');
        const fieldsContainer = document.getElementById('formFields');
        const title = document.getElementById('modalTitle');
        const form = document.getElementById('pioneerForm');

        // Reset state for "Create" mode
        form.reset();
        document.getElementById('form_mode').value = 'create';
        document.getElementById('edit_record_id').value = '';
        
        title.innerText = `New ${entityType.toUpperCase()} Entry`;
        fieldsContainer.innerHTML = this.getSchema(entityType);
        
        modal.style.display = 'block';
    },

    // 2. REGISTRY: Opens the Master Registry Modal and fetches list
    openRegistry: function(entityType) {
        const modal = document.getElementById('masterRegistryModal');
        const title = document.getElementById('registryTitle');
        
        title.innerText = `${entityType.toUpperCase()} REGISTRY`;
        modal.style.display = 'block';
        modal.focus();

        fetch(`/api/list/${entityType}/`)
            .then(res => res.json())
            .then(response => {
                this.renderTable(entityType, response.data);
            })
            .catch(err => console.error("Sync Error:", err));
    },

    // 3. RENDERER: Builds the high-density grid with capabilities
    renderTable: function(type, data) {
        const headerRow = document.getElementById('registryHeaders');
        const body = document.getElementById('registryBody');
        
        if (!data || data.length === 0) {
            body.innerHTML = '<tr><td colspan="100%" style="text-align:center; padding:20px;">Ledger is empty.</td></tr>';
            return;
        }

        const columns = Object.keys(data[0]);
        headerRow.innerHTML = columns.map(c => `<th>${c.toUpperCase().replace('_', ' ')}</th>`).join('') + '<th>CAPABILITIES</th>';

        body.innerHTML = data.map(item => `
            <tr>
                ${columns.map(c => `<td>${item[c] !== null ? item[c] : '-'}</td>`).join('')}
                <td class="capability-btns">
                    <button onclick="PioneerController.hydrateEdit('${type}', '${item.id}')" title="Edit">✏️ Edit</button>
                    <button onclick="PioneerController.deleteRecord('${type}', '${item.id}')" title="Delete">🗑️</button>
                </td>
            </tr>
        `).join('');
		
		// Inside PioneerController.renderTable...
		body.innerHTML = data.map(item => {
			// Find the value of the primary key safely
			// It's usually the first column or contains 'id'
			const recordId = item.id || item.bank_account_id || item.gl_account_id || item.supplier_id || item.product_id;

			return `
				<tr>
					${columns.map(c => `<td>${item[c] !== null ? item[c] : '-'}</td>`).join('')}
					<td>
						<button onclick="PioneerController.hydrateEdit('${type}', '${recordId}')">✏️ Edit</button>
						<button onclick="PioneerController.deleteRecord('${type}', '${recordId}')">🗑️</button>
					</td>
				</tr>
			`;
		}).join('');
    },

    // 4. HYDRATION: Pulls data, opens form, and injects values
    hydrateEdit: function(type, id) {
        fetch(`/api/detail/${type}/${id}/`)
            .then(res => res.json())
            .then(response => {
                const data = response.data;
                
                // First, prepare the form with the right fields
                this.openEntryForm(type); 
                
                // Change to Edit Mode
                document.getElementById('modalTitle').innerText = `Edit ${type.toUpperCase()}: ${id}`;
                document.getElementById('form_mode').value = 'edit';
                document.getElementById('edit_record_id').value = id;
                
                // Inject the values
                Object.keys(data).forEach(key => {
                    const el = document.querySelector(`#pioneerForm [name="${key}"]`);
                    if (el) el.value = data[key];
                });

                // Hide the registry so the user can focus on the edit
                document.getElementById('masterRegistryModal').style.display = 'none';
            });
    },

    // 5. SCHEMAS: The Complete Field Blueprints for the UN Accounting System
    getSchema: function(type) {
        const schemas = {
            'user': `
                <div class="form-group">
                    <label>Username</label><input type="text" name="username" required class="pioneer-input">
                    <label>Password</label><input type="password" name="password" required class="pioneer-input">
                    <label>Designation</label><input type="text" name="designation" class="pioneer-input">
                    <label>Email</label><input type="email" name="email" class="pioneer-input">
                    <label>Phone</label><input type="text" name="phone" class="pioneer-input">
                    <label>Address</label><input type="text" name="contact_address" class="pioneer-input">
                    <label>Access Level ID</label><input type="number" name="access_level_id" class="pioneer-input" value="1">
                </div>`,

            'bank': `
                <div class="form-group">
                    <label>Bank Account ID</label><input type="text" name="bank_account_id" required class="pioneer-input">
                    <label>Account Number</label><input type="text" name="account_number" required class="pioneer-input">
                    <label>Description/Bank Name</label><input type="text" name="description" class="pioneer-input">
                    <label>Email</label><input type="email" name="email" class="pioneer-input">
                    <label>Phone</label><input type="text" name="phone" class="pioneer-input">
                    <label>Address</label><input type="text" name="contact_address" class="pioneer-input">
                </div>`,

            'supplier': `
                <div class="form-group">
                    <label>Supplier ID</label><input type="text" name="supplier_id" required class="pioneer-input">
                    <label>Bank Account No</label><input type="text" name="bank_account_number" class="pioneer-input">
                    <label>Description</label><input type="text" name="description" class="pioneer-input">
                    <label>Email</label><input type="email" name="email" class="pioneer-input">
                    <label>Phone</label><input type="text" name="phone" class="pioneer-input">
                    <label>Address</label><input type="text" name="contact_address" class="pioneer-input">
                </div>`,

            'gl': `
                <div class="form-group">
                    <label>GL Account ID</label><input type="text" name="gl_account_id" required class="pioneer-input">
                    <label>Description</label><input type="text" name="description" required class="pioneer-input">
                    <label>Debit/Credit</label>
                    <select name="debit_credit" class="pioneer-input">
                        <option value="Debit">Debit</option>
                        <option value="Credit">Credit</option>
                    </select>
                    <label>Currency</label><input type="text" name="currency" value="US$" class="pioneer-input">
                    <label>Current Amount</label><input type="number" step="0.01" name="amount" class="pioneer-input">
                </div>`,

            'analysis': `
                <div class="form-group">
                    <label>Category Name</label><input type="text" name="category_name" required class="pioneer-input">
                    <label>Code Reference</label><input type="text" name="code_ref" class="pioneer-input">
                </div>`,

            'task': `
                <div class="form-group">
                    <label>Task/Project ID</label><input type="text" name="project_id" required class="pioneer-input">
                    <label>Task Description</label><textarea name="description" class="pioneer-input"></textarea>
                    <label>Assigned To</label><input type="text" name="assigned_to" class="pioneer-input">
                    <label>Status</label>
                    <select name="status" class="pioneer-input">
                        <option value="pending">Pending</option>
                        <option value="in_progress">In Progress</option>
                        <option value="completed">Completed</option>
                    </select>
                </div>`,

            'build': `
                <div class="form-group">
                    <label>Build Category</label><input type="text" name="build_name" required class="pioneer-input">
                    <label>Specifications</label><input type="text" name="specs" class="pioneer-input">
                </div>`,

            'product': `
                <div class="form-group">
                    <label>Product ID</label><input type="text" name="product_id" required class="pioneer-input">
                    <label>Product Name</label><input type="text" name="product_name" required class="pioneer-input">
                    <label>Unit Price</label><input type="number" step="0.01" name="unit_price" class="pioneer-input">
                    <label>Stock Level</label><input type="number" name="stock_qty" class="pioneer-input">
                </div>`
        };
        return schemas[type] || '<p class="error-msg">⚠️ System Error: Entity schema not found in registry.</p>';
    },

    deleteRecord: function(type, id) {
        if(confirm(`Confirm deletion of ${type} record ${id}?`)) {
            fetch(`/api/delete/${type}/${id}/`, { method: 'DELETE' })
            .then(() => this.openRegistry(type)); // Refresh list after delete
        }
    }
};

// Global Listeners
document.addEventListener('keydown', (e) => {
    if (e.key === "Escape") {
        document.getElementById('masterRegistryModal').style.display = 'none';
        document.getElementById('pioneerModal').style.display = 'none';
    }
});