from odoo import models, fields, api
from datetime import datetime, time


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    # Override the date_deadline field to include time
    date_deadline = fields.Datetime(
        string='Due Date',
        required=True,
        index=True,
        default=fields.Datetime.now
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle datetime/date comparison issue"""
        # Call parent's parent (models.Model) to skip the problematic filtering
        activities = super(models.Model, self).create(vals_list)

        # Replicate the parent logic but with datetime comparison
        # Convert Date.today() to datetime for proper comparison
        today_datetime = fields.Datetime.to_datetime(
            datetime.combine(fields.Date.today(), time.max)
        )

        todo_activities = activities.filtered(
            lambda act: act.active and act.date_deadline and act.date_deadline <= today_datetime
        )

        if todo_activities:
            todo_activities.action_feedback_schedule_next()

        return activities

    def unlink(self):
        """Override unlink to handle datetime/date comparison issue"""
        # Convert Date.today() to datetime for proper comparison
        today_datetime = fields.Datetime.to_datetime(
            datetime.combine(fields.Date.today(), time.max)
        )

        todo_activities = self.filtered(
            lambda act: act.active and act.date_deadline and act.date_deadline <= today_datetime
        )

        if todo_activities:
            for user, user_activities in todo_activities.grouped('user_id').items():
                user._bus_send("mail.activity/updated", {"activity_deleted": True, "count_diff": -len(user_activities)})

        return super(MailActivity, self).unlink()

