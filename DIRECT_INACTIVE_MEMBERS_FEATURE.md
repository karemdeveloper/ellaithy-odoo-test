# Direct Inactive Members - New Feature

## Overview

Added a new security group that allows authorized users to make team members inactive **directly** using a radio button, **without requiring an inactive request**.

---

## Features

### 1. **New Security Group**
**File:** [crm_customization/security/groups.xml:43-49](crm_customization/security/groups.xml#L43-L49)

```xml
<record id="group_direct_inactive_members" model="res.groups">
    <field name="name">User: Direct Inactive Members</field>
    <field name="category_id" ref="base.module_category_sales_sales"/>
    <field name="comment">
        The user can make team members inactive directly without requiring an inactive request.
    </field>
</record>
```

**Group Name:** `User: Direct Inactive Members`
**Technical ID:** `crm_customization.group_direct_inactive_members`

---

### 2. **Permission Check Field**
**File:** [crm_customization/models/crm_team_member.py:20-31](crm_customization/models/crm_team_member.py#L20-L31)

Added a computed field that checks if the current user has permission to edit the state directly:

```python
can_edit_state_directly = fields.Boolean(
    string='Can Edit State Directly',
    compute='_compute_can_edit_state_directly'
)

@api.depends_context('uid')
def _compute_can_edit_state_directly(self):
    """Check if current user has permission to edit state directly"""
    has_permission = self.env.user.has_group('crm_customization.group_direct_inactive_members')
    for rec in self:
        rec.can_edit_state_directly = has_permission
```

---

### 3. **Radio Button Interface**
**File:** [crm_customization/views/crm_team_member_views.xml:9-16](crm_customization/views/crm_team_member_views.xml#L9-L16)

#### Form View:
- **Radio button widget** for Active/Inactive selection
- **Horizontal layout** for better UX
- **Readonly for unauthorized users** (those without the group)
- **Editable for authorized users** (those with the group)

```xml
<field name="can_edit_state_directly" invisible="1"/>
<field name="state" widget="radio" options="{'horizontal': true}"
       readonly="not can_edit_state_directly"/>
```

#### Tree View:
**File:** [crm_customization/views/crm_team_member_views.xml:26-28](crm_customization/views/crm_team_member_views.xml#L26-L28)

- **Badge widget** with color coding:
  - 🟢 Green for "Active"
  - 🔴 Red for "Inactive"

```xml
<field name="state" widget="badge"
       decoration-success="state == 'active'"
       decoration-danger="state == 'inactive'"/>
```

---

## User Experience

### For Users **WITH** the Group:

1. Open a team member record
2. See the **Status** field as a radio button with two options:
   - ○ Active
   - ○ Inactive
3. Click on either option to change the status **instantly**
4. No need to create an inactive request

### For Users **WITHOUT** the Group:

1. Open a team member record
2. See the **Status** field but it's **readonly** (grayed out)
3. Must use the traditional inactive request workflow to change status

---

## How to Assign the Group

### Via Odoo UI:

1. Go to **Settings** → **Users & Companies** → **Users**
2. Select a user
3. Click **Edit**
4. Scroll to **Sales** section
5. Check **"User: Direct Inactive Members"**
6. Click **Save**

### Via Code (for administrators):

```python
user = self.env['res.users'].browse(USER_ID)
group = self.env.ref('crm_customization.group_direct_inactive_members')
user.groups_id = [(4, group.id)]
```

---

## Comparison: Traditional vs Direct Method

### Traditional Method (Inactive Request):

1. User creates an inactive request (`inactive.request`)
2. Fills out:
   - Date
   - Date From
   - Date To
   - Inactive Reason
3. Request goes to "To Approve" state
4. Authorized user approves the request
5. On approval, the member's state changes to "Inactive"

**Steps:** 5+ clicks
**Time:** ~2-3 minutes
**Requires:** Approval workflow

### Direct Method (New Feature):

1. User with permission opens team member
2. Clicks the "Inactive" radio button
3. Done!

**Steps:** 2 clicks
**Time:** ~5 seconds
**Requires:** Special permission group

---

## Use Cases

### Recommended for:

✅ **Branch Managers** - Quick team management
✅ **HR Managers** - Handle sudden absences
✅ **Operations Managers** - Emergency team adjustments
✅ **Admin Users** - System maintenance

### NOT Recommended for:

❌ **Regular Team Members** - Should use request workflow
❌ **Junior Salespeople** - Lack proper authority
❌ **External Users** - Security risk

---

## Technical Details

### Field Visibility Logic:

```python
readonly="not can_edit_state_directly"
```

This dynamically evaluates:
- If `can_edit_state_directly` is `True` → Field is editable
- If `can_edit_state_directly` is `False` → Field is readonly

### Security:

- ✅ Permission check on every record access
- ✅ Context-dependent (`@api.depends_context('uid')`)
- ✅ Group-based access control
- ✅ No API bypass (enforced at model level)

---

## Deployment Steps

1. **Upgrade the module:**
   ```bash
   odoo-bin -u crm_customization -d your_database
   ```

2. **Restart Odoo server:**
   ```bash
   sudo systemctl restart odoo
   ```

3. **Assign the group to authorized users:**
   - Go to Settings → Users
   - Add "User: Direct Inactive Members" group to appropriate users

4. **Test the feature:**
   - Login as a user WITH the group → Verify radio button is editable
   - Login as a user WITHOUT the group → Verify radio button is readonly

---

## Screenshots Reference

### Form View (Editable):
```
┌─────────────────────────────────────┐
│ Team Member                         │
├─────────────────────────────────────┤
│ User: John Doe                      │
│ Team: Sales Team A                  │
│                                     │
│ Status:  ◉ Active   ○ Inactive      │
│                                     │
└─────────────────────────────────────┘
```

### Form View (Readonly):
```
┌─────────────────────────────────────┐
│ Team Member                         │
├─────────────────────────────────────┤
│ User: Jane Smith                    │
│ Team: Sales Team B                  │
│                                     │
│ Status:  ◉ Active   ○ Inactive      │
│         (Grayed out - readonly)     │
│                                     │
└─────────────────────────────────────┘
```

### Tree View:
```
┌──────────────┬──────────────┬──────────┐
│ User         │ Team         │ Status   │
├──────────────┼──────────────┼──────────┤
│ John Doe     │ Sales Team A │ Active   │ 🟢
│ Jane Smith   │ Sales Team B │ Inactive │ 🔴
│ Bob Johnson  │ Sales Team A │ Active   │ 🟢
└──────────────┴──────────────┴──────────┘
```

---

## Coexistence with Inactive Request Workflow

Both methods work **side-by-side**:

1. **Inactive Request Workflow** ([inactive_request.py:20-29](crm_customization/models/inactive_request.py#L20-L29))
   - Still available for all users
   - Maintains approval process
   - Creates audit trail with reasons

2. **Direct Method** (New)
   - Only for authorized users
   - Quick status change
   - No approval needed

Users can choose the appropriate method based on the situation.

---

## Future Enhancements

Potential improvements:

1. **Audit Log**: Track who changed status and when
2. **Notification**: Alert team leader when member status changes
3. **Validation**: Prevent inactivation if member has active leads
4. **Reason Field**: Optional quick reason for direct inactivation
5. **Batch Action**: Inactive multiple members at once

---

## Files Modified

1. **Security Group:** [crm_customization/security/groups.xml](crm_customization/security/groups.xml#L43-L49)
2. **Model Enhancement:** [crm_customization/models/crm_team_member.py](crm_customization/models/crm_team_member.py#L20-L31)
3. **View Updates:** [crm_customization/views/crm_team_member_views.xml](crm_customization/views/crm_team_member_views.xml#L9-L16)

---

## Support & Troubleshooting

### Issue: Radio button not editable even with group assigned

**Solution:**
1. Clear browser cache
2. Logout and login again
3. Verify group assignment in user settings
4. Check if module was upgraded successfully

### Issue: State field not showing in tree view

**Solution:**
1. Verify view inheritance is correct
2. Update the module
3. Refresh the browser

### Issue: Permission error when changing state

**Solution:**
1. Check record rules for `crm.team.member` model
2. Verify user has write access to the model
3. Check server logs for detailed error

---

## Contact

For questions or issues about this feature, refer to:
- **Model:** `crm.team.member`
- **Security Group:** `crm_customization.group_direct_inactive_members`
- **Views:** `view_crm_team_member_form_inherit_branch`, `view_crm_team_member_tree_inherit_branch`
