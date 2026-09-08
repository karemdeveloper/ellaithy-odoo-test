from markupsafe import Markup

from odoo import _, api, models


class EmployeeChildAudit(models.AbstractModel):
    _name = 'ellithy.employee.child.audit'
    _description = 'Employee child record audit'

    # Fields always shown on an "Updated" log even when unchanged, so a
    # change to one field (e.g. a replaced file) still identifies which
    # record it belongs to (e.g. which document type).
    _audit_context_fields = ()

    def _audit_snapshot(self):
        self.ensure_one()
        values = {}
        for name, field in self._fields.items():
            if (name in ('id', 'create_uid', 'create_date', 'write_uid',
                         'write_date', 'employee_id') or not field.store
                    or field.compute or field.related):
                continue
            value = self[name]
            if field.type == 'binary':
                value = _('File attached') if value else _('No file')
            elif field.type in ('many2one', 'one2many', 'many2many'):
                value = ', '.join(value.mapped('display_name'))
            elif field.type == 'selection':
                value = dict(field._description_selection(self.env)).get(value, value)
            values[name] = (field.string, str(value) if value is not False else '—')
        return values

    def _post_child_audit(self, employee, operation, values):
        rows = [Markup('<li><b>%s</b>: %s</li>') % (label, value)
                for label, value in values.values()]
        employee.message_post(
            body=Markup('<p>%s — %s</p><ul>%s</ul>') % (
                self._description, operation, Markup('').join(rows)),
            subtype_xmlid='mail.mt_note')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._post_child_audit(record.employee_id, _('Created'), record._audit_snapshot())
        return records

    def write(self, vals):
        before = {r.id: (r.employee_id, r._audit_snapshot()) for r in self}
        # Binary contents are deliberately not copied to the chatter.
        binary_changed = {r.id: {n for n in vals if n in r._fields
                               and r._fields[n].type == 'binary' and r[n] != vals[n]}
                          for r in self}
        result = super().write(vals)
        for record in self:
            old_employee, old = before[record.id]
            new = record._audit_snapshot()
            changed = {n: (label, '%s → %s' % (old.get(n, ('', '—'))[1], value))
                       for n, (label, value) in new.items()
                       if old.get(n) != (label, value) or n in binary_changed[record.id]}
            if old_employee != record.employee_id:
                changed['employee_id'] = (_('Employee'), '%s → %s' % (
                    old_employee.display_name, record.employee_id.display_name))
            if changed:
                context = {n: new[n] for n in record._audit_context_fields
                           if n in new and n not in changed}
                entry = {**context, **changed}
                for employee in old_employee | record.employee_id:
                    record._post_child_audit(employee, _('Updated'), entry)
        return result

    def unlink(self):
        snapshots = [(r.employee_id, r._audit_snapshot()) for r in self]
        result = super().unlink()
        for employee, values in snapshots:
            self._post_child_audit(employee, _('Deleted'), values)
        return result
