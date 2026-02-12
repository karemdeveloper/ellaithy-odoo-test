# CRM Lead Sequence Module

## Overview
This module provides custom sequencing for CRM opportunities based on branch, year, and month.

## Features
- **Custom Sequence Format**: `BranchCode/Year/Month/0001`
  - Example: `NYC/2026/02/0001`
- **Automatic Generation**: Sequences are automatically assigned when creating new opportunities
- **Monthly Reset**: Sequence counter resets each month per branch
- **Dynamic Sequences**: Creates `ir.sequence` records on-the-fly for each branch/month combination
- **Existing Data Update**: Automatically updates all existing leads with proper sequences on installation

## Sequence Logic
- Each branch gets its own sequence per month
- Sequences are stored as `ir.sequence` with code: `crm.lead.{branch_id}.{year}.{month}`
- Numbers are padded to 4 digits (0001, 0002, etc.)
- If branch code is not set, defaults to 'XX'

## Installation
1. Ensure `crm_customization` module is installed (depends on `res.branch` model)
2. Install this module
3. All existing leads will be automatically updated with new sequences
4. New opportunities will receive sequences automatically

## Dependencies
- `crm`
- `crm_customization` (for `res.branch` model with `branch_code` field)

## Technical Details
- Uses hybrid approach combining `ir.sequence` with custom formatting
- Sequences are created dynamically per branch/month
- Update function preserves chronological order when assigning sequences to existing records

## Manual Update
If you need to manually update existing leads again:
```python
self.env['crm.lead'].action_update_existing_leads()
```
