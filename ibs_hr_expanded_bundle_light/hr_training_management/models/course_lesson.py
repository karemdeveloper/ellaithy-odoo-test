# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CourseLesson(models.Model):
    _name = 'course.lesson'
    _description = 'Course Lesson'
    _order = 'course_id, sequence, id'

    course_id = fields.Many2one('course.course', string='Course',
                                 required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)  # [Claude addition]
    title = fields.Char(string='Title', required=True)

    video_type = fields.Selection([
        ('uploaded', 'Uploaded'),
        ('youtube', 'YouTube'),
        ('vimeo', 'Vimeo'),
        ('url', 'URL'),
    ], string='Video Type', required=True, default='uploaded')

    video_url = fields.Char(string='Video URL')
    video_file = fields.Binary(string='Video File', attachment=True)
    video_file_filename = fields.Char(string='Video Filename')  # [Claude addition]

    duration = fields.Float(string='Duration (Minutes)')

    free_lesson = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No'),
    ], string='Free Lesson', default='no')

    description = fields.Html(string='Description')
    active = fields.Boolean(default=True)  # [Claude addition]

    @api.constrains('video_type', 'video_url', 'video_file')
    def _check_video_source(self):
        for lesson in self:
            if lesson.video_type == 'uploaded' and not lesson.video_file:
                raise ValidationError(_('Please upload a Video File for an Uploaded lesson.'))
            if lesson.video_type in ('youtube', 'vimeo', 'url') and not lesson.video_url:
                raise ValidationError(_('Please provide a Video URL for this Video Type.'))
