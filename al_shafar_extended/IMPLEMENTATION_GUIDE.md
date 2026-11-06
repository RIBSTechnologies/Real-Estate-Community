# Al-Shafar Extended - Analytic Account Automatic Setup Implementation Guide

## Overview

This implementation adds comprehensive automatic analytic account creation and invoice mapping functionality to the `al_shafar_extended` module. The system creates a hierarchical analytic structure based on Residential Types, Buildings, and Units, and automatically maps invoices to the correct analytic accounts.

## Architecture

### Analytic Hierarchy Structure

```
Residential Type
    ↓
Analytic Plan
    ↓
Residential Type Analytic Account (Parent)
    ↓
    ├── Building Analytic Account (Child)
    │   ├── Unit 001 Analytic Account (Grandchild)
    │   ├── Unit 002 Analytic Account (Grandchild)
    │   └── Unit 003 Analytic Account (Grandchild)
    │
    └── Building 2 Analytic Account (Child)
        ├── Unit 001 Analytic Account (Grandchild)
        └── Unit 002 Analytic Account (Grandchild)
```

### Example with Actual Data

```
Residential
├── Residential Analytic Plan
└── Residential Analytic Account
    ├── Villa A Account
    │   ├── Unit 001 Account
    │   ├── Unit 002 Account
    │   └── Unit 003 Account
    └── Villa B Account
        ├── Unit 001 Account
        └── Unit 002 Account
```

## Components Implemented

### 1. **residential.type Model** (`models/analytic_setup.py`)

**Purpose:** Define property types and their associated analytic structures.

**Features:**
- Stores 4 predefined property types: Residential, Villa, Commercial, Land
- Each type automatically gets an associated Analytic Plan and Analytic Account
- Prevents duplicates using unique constraint
- Auto-creates analytic structures on record creation

**Fields:**
- `name`: Property type name (Unique)
- `analytic_plan_id`: Associated analytic plan
- `analytic_account_id`: Associated analytic account (parent account)
- `active`: Status flag

**Key Method:**
```python
_create_default_residential_types()
```
Creates the four default residential types with their analytic structures if they don't exist.

### 2. **PropertyProject Model Extension** (`models/analytic_setup.py`)

**Purpose:** Enhance Building creation to automatically create building-level analytic accounts.

**New Field:**
- `residential_type_id`: Links building to a residential type

**Key Behavior:**
1. When a Building is created:
   - Automatically creates `project_id` (existing functionality)
   - Creates `building_account_id` as a child of the Residential Type account
   - Links building to matching residential type

2. When Building name is updated:
   - Automatically updates the building account name

**Hierarchy Created:**
```
Residential Type Account
    └── Building A Account
```

### 3. **PropertyDetails Model Extension** (`models/analytic_setup.py`)

**Purpose:** Enhance Unit creation to automatically create unit-level analytic accounts.

**Key Behavior:**
1. When a Unit is created:
   - Automatically creates `unit_account_id`
   - Links unit account as child of building account
   - Prevents duplicate accounts with intelligent search

2. When Unit name is updated:
   - Automatically updates the unit account name

**Hierarchy Created:**
```
Building Account
    └── Unit 001 Account
```

### 4. **AccountMove Model Extension** (`models/account_move.py`)

**Purpose:** Automatically populate analytic accounts in invoices based on contracts/units.

**Key Methods:**

#### `create(vals_list)`
- Intercepts invoice creation
- Automatically populates analytic accounts if the invoice is linked to a tenancy

#### `_get_applicable_analytic_accounts()`
- Determines which analytic accounts should be used for an invoice
- Builds hierarchy: Unit → Building → Residential Type
- Returns the most specific applicable account (Unit account if available)

#### `_populate_line_analytic_distribution(analytic_accounts)`
- Populates the `analytic_distribution` field in invoice lines
- Distributes the 100% allocation to the appropriate account
- Only updates lines that don't already have analytic distribution

#### `_get_analytic_account_domain()`
- Generates a restricted domain for analytic account selection
- Shows only relevant accounts:
  - Unit account
  - Building account
  - Residential type account
  - Parent accounts of the above
- **Prevents unrelated accounts from appearing** in dropdown selections

## Automatic Data Creation Sequence

### 1. **Module Installation**
- `init_residential_types.xml` creates 4 residential type records
- Each record triggers creation of:
  - Analytic Plan: `{Type Name} Plan`
  - Analytic Account: `{Type Name}`

### 2. **Building Creation**
```
Building Created (e.g., "Villa A")
    ↓
Automatically:
1. Create Project "Villa A"
2. Create Analytic Plan "Villa A Plan" (if not exists)
3. Create Analytic Account "Villa A" linked to parent Residential account
4. Link Building → project_id
5. Link Building → building_account_id
6. Link Building → residential_type_id
```

### 3. **Unit Creation**
```
Unit Created (e.g., "Unit 001")
    ↓
Automatically:
1. Link Unit → property_project_id (Building)
2. Create Analytic Account "Unit 001"
3. Link as child of Building account
4. Link Unit → unit_account_id
5. Generate Unit Sequence (existing functionality)
```

### 4. **Contract → Invoice Creation**
```
Contract Created → Active
    ↓
Invoice Created for Contract
    ↓
Automatically:
1. Detect linked Tenancy/Unit
2. Get Unit Analytic Account
3. Get Building Analytic Account
4. Get Residential Type Account
5. Populate invoice lines with Unit account (most specific)
6. Restrict analytic account domain to relevant accounts only
```

## Domain Restriction for Invoice Analytic Accounts

### Problem Addressed
Without restriction, users see **all** analytic accounts in dropdown selections, including:
- Unrelated buildings
- Unrelated units
- Unrelated property types
- Complete hierarchy noise

### Solution Implemented
The `_get_analytic_account_domain()` method generates a restricted domain that shows only:

```
For Invoice with Unit 005 in Building A (Residential):
├── Unit 005 Account ✓ (most specific)
├── Building A Account ✓
├── Residential Account ✓
└── [All other accounts from hierarchy] ✓
```

**Example - Invalid Accounts Excluded:**
```
Building B ✗
Unit 101 in Building B ✗
Commercial Account ✗
Land Account ✗
Villa Account ✗
```

## Duplicate Prevention

The implementation prevents duplicate analytic accounts through:

1. **Unique Residential Type Names**
   ```python
   _sql_constraints = [('name_unique', 'unique(name)', 'Property Type name must be unique!')]
   ```

2. **Building Account Search Before Creation**
   - Checks if building account already exists for that building
   - Reuses existing account instead of duplicating

3. **Unit Account Smart Search**
   ```python
   existing_account = search([
       ('name', '=', unit.name),
       ('plan_id', '=', plan_id),
       ('parent_id', '=', parent_account_id),  # Must be child of building
   ])
   ```

## Integration with Existing Functionality

### Preserved Existing Features
- ✓ Automatic Project creation on Building creation
- ✓ Automatic Analytic Plan creation on Building creation
- ✓ Automatic Analytic Account creation on Building creation
- ✓ Unit Sequence generation (no changes)
- ✓ Contract creation and management (no changes)
- ✓ Invoice generation (no changes to base flow)

### Enhanced Functionality
- ✓ Building accounts now have proper hierarchical parent (Residential Type)
- ✓ Unit accounts now have proper hierarchical parent (Building)
- ✓ Invoices automatically populate analytic accounts
- ✓ Analytic account selection restricted to relevant accounts

## File Structure

```
al_shafar_extended/
├── models/
│   ├── __init__.py                    (Updated - added analytic_setup import)
│   ├── account_move.py                (Enhanced - auto-populate & domain restriction)
│   ├── analytic_setup.py              (NEW - ResidentialType, PropertyProject, PropertyDetails)
│   ├── contract_contract.py
│   ├── tenancy_details.py
│   ├── property_details.py
│   └── ...
├── views/
│   ├── residential_type_views.xml     (NEW - Model views and menu)
│   └── ...
├── data/
│   ├── init_residential_types.xml     (NEW - Initialize 4 types)
│   └── sequence.xml
├── security/
│   ├── ir.model.access.csv            (Updated - added residential.type access)
│   └── security_groups.xml
├── __manifest__.py                     (Updated - added new data & views)
└── IMPLEMENTATION_GUIDE.md             (This file - NEW)
```

## Configuration Steps

### 1. **Installation**
```bash
odoo-bin --update al_shafar_extended
```

### 2. **Verify Residential Types**
1. Go to **Accounting → Property Types**
2. Should see 4 types: Residential, Villa, Commercial, Land
3. Each should have linked Analytic Plan and Account

### 3. **Create/Update Buildings**
1. Go to **Property Management → Buildings**
2. Create or update a building
3. Verify:
   - `project_id` is set
   - `building_account_id` is set
   - `residential_type_id` is set

### 4. **Create/Update Units**
1. Create or update a unit under a building
2. Verify:
   - `unit_account_id` is set
   - Building has `building_account_id` set

### 5. **Create Invoices**
1. Create a contract for a unit
2. Generate invoice
3. Verify:
   - Invoice lines have `analytic_distribution` populated
   - Analytic account dropdown shows only relevant accounts

## Testing Scenarios

### Scenario 1: Building Creation
```
1. Create Building "Villa A" with property_type = 'Residential'
2. Expected:
   - Project "Villa A" created
   - Analytic Account "Villa A" created
   - building_account_id set
   - residential_type_id → Residential type
   - Hierarchy: Residential Account → Villa A Account
```

### Scenario 2: Unit Creation
```
1. Create Unit "001" under "Villa A"
2. Expected:
   - Analytic Account "001" created
   - unit_account_id set
   - Parent: Villa A Account
   - Hierarchy: Villa A Account → 001 Account
```

### Scenario 3: Invoice Creation
```
1. Create Contract for Unit 001 in Villa A
2. Create Invoice for Contract
3. Expected:
   - Invoice lines have analytic_distribution
   - Analytic account = Unit 001 Account
   - Analytic domain restricted to: Unit, Building, Residential Type accounts
   - Other buildings/units NOT in dropdown
```

### Scenario 4: Duplicate Prevention
```
1. Create Building "Villa A"
   - Generates Account "Villa A"
2. Edit Building "Villa A" name → stays "Villa A"
   - No new account created
3. Create another building with same name (system shouldn't allow or should handle)
   - Existing account reused
```

## Error Handling

All automatic operations include try-catch blocks with logging:

```python
try:
    # Create analytic account
except Exception as e:
    _logger.warning(f"Failed to create building analytic account: {str(e)}")
    # Building creation continues despite error
```

This ensures:
- Building/Unit creation never fails due to analytic setup
- Errors are logged for troubleshooting
- Fallback logic available

## Limitations & Future Enhancements

### Current Limitations
1. Invoice analytic distribution uses single account (100%)
   - Could be enhanced to distribute across hierarchy

2. Domain restriction is computed on-the-fly
   - Could be cached for performance

### Future Enhancements
1. Split distribution across hierarchy:
   ```
   Unit 001 Account: 50%
   Building Account: 30%
   Residential Type Account: 20%
   ```

2. Configurable analytic distribution methods

3. Analytic account template/pattern configuration

## Troubleshooting

### Issue: Building created but `building_account_id` is empty
**Solution:**
1. Check if Residential Types exist: **Accounting → Property Types**
2. Manually trigger: Select building → Set `residential_type_id` → Save
3. Check server logs for errors

### Issue: Unit account not created
**Solution:**
1. Verify building has `building_account_id` set
2. Check building's Analytic Plan exists
3. Create unit again or use admin to manually set `unit_account_id`

### Issue: Invoice showing all analytic accounts in dropdown
**Solution:**
1. Ensure invoice is linked to `tenancy_id`
2. Ensure tenancy has `property_id` set
3. Refresh browser cache
4. Check domain logic in form view

## Support & Maintenance

For questions or issues:
1. Check logs: `var/log/odoo.log`
2. Review the Implementation Guide above
3. Verify data integrity using database queries
4. Test in development environment first

## Conclusion

This implementation provides:
- ✓ Automatic hierarchical analytic account creation
- ✓ No duplicate accounts
- ✓ Automatic invoice-to-account mapping
- ✓ Restricted account selection (relevant accounts only)
- ✓ Full integration with existing Odoo workflows
- ✓ No modifications to `al_shafar_base` module
- ✓ Complete within `al_shafar_extended` using proper inheritance
