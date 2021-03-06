##############################################################################
#
#    Copyright (C) 2018 Compassion CH (http://www.compassion.ch)
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
import logging
from base64 import b64decode, b64encode

from werkzeug.datastructures import FileStorage

from odoo import models, fields, _

_logger = logging.getLogger(__name__)

try:
    import magic
except ImportError:
    _logger.warning("Please install magic in order to use Muskathlon module")


class OrderMaterialForm(models.AbstractModel):
    _name = "cms.form.order.material.mixin"
    _inherit = "cms.form"

    _form_model = "crm.lead"
    _form_model_fields = ["partner_id", "description"]
    _form_required_fields = ["flyer_number"]

    partner_id = fields.Many2one("res.partner", readonly=False)
    event_id = fields.Many2one("crm.event.compassion", readonly=False)
    form_id = fields.Char()
    flyer_number = fields.Selection(
        [("5", "5"), ("10", "10"), ("15", "15"), ("20", "20"), ("30", "30"), ],
        "Number of flyers",
    )
    large_picture = fields.Binary()

    @property
    def _form_fieldsets(self):
        fields = [
            {"id": "flyers", "fields": ["flyer_number", "form_id"]},
        ]
        if not self.large_picture:
            fields.append(
                {
                    "id": "picture",
                    "description": _(
                        "Please upload a large image of good quality which "
                        "will be used to be printed on your material."
                    ),
                    "fields": ["large_picture"],
                }
            )
        return fields

    @property
    def form_msg_success_created(self):
        return _(
            "Thank you for your request. You will hear back from us "
            "within the next days."
        )

    @property
    def form_widgets(self):
        # Hide fields
        res = super(OrderMaterialForm, self).form_widgets
        if self.large_picture:
            pic_widget = "cms_form_compassion.form.widget.hidden"
        else:
            pic_widget = "cms_form_compassion.form.widget.simple.image.required"
        res.update(
            {
                "form_id": "cms_form_compassion.form.widget.hidden",
                "partner_id": "cms_form_compassion.form.widget.hidden",
                "event_id": "cms_form_compassion.form.widget.hidden",
                "description": "cms_form_compassion.form.widget.hidden",
                "large_picture": pic_widget,
            }
        )
        return res

    def form_init(self, request, main_object=None, **kw):
        form = super(OrderMaterialForm, self).form_init(request, main_object, **kw)
        # Set default values
        registration = kw.get("registration")
        form.partner_id = registration and registration.partner_id
        form.event_id = registration and registration.compassion_event_id
        form.large_picture = form.partner_id.advocate_details_id.picture_large
        return form

    def form_before_create_or_update(self, values, extra_values):
        """ Dismiss any pending status message, to avoid multiple
        messages when multiple forms are present on same page.
        """
        super(OrderMaterialForm, self).form_before_create_or_update(
            values, extra_values
        )
        self.o_request.website.get_status_message()
        large_picture = self.o_request.params.get("large_picture")
        partner = self.partner_id.sudo()
        if large_picture:
            if isinstance(large_picture, FileStorage):
                large_picture.stream.seek(0)
                large_picture = large_picture.stream.read()
            partner.advocate_details_id.picture_large = b64encode(large_picture)
            partner.registration_ids[:1].write(
                {
                    "completed_task_ids": [
                        (4, partner.env.ref("muskathlon.task_picture").id)
                    ]
                }
            )
            extra_values["large_picture"] = large_picture
        else:
            extra_values[
                "large_picture"
            ] = partner.advocate_details_id.picture_large
        staff_id = (
            self.env["res.config.settings"]
                .sudo()
                .get_param("muskathlon_order_notify_id")
        )
        values.update(
            {
                "name": "Muskathlon material order - {}".format(
                    self.partner_id.name
                ),
                "description": "Number of flyers wanted: "
                               + extra_values["flyer_number"],
                "user_id": staff_id,
                "event_id": self.event_id.id,
                "partner_id": self.partner_id.id,
            }
        )

    def _form_create(self, values):
        """ Run as Muskathlon user to authorize lead creation. """
        uid = self.env.ref("muskathlon.user_muskathlon_portal").id
        self.main_object = self.form_model.sudo(uid).create(values.copy())

    def form_after_create_or_update(self, values, extra_values):
        super(OrderMaterialForm, self).form_after_create_or_update(
            values, extra_values
        )
        # Update contact fields on lead
        self.main_object._onchange_partner_id()
        # Send mail
        picture = extra_values["large_picture"]
        email_template = self.env.ref("muskathlon.order_material_mail_template2")
        email_template.sudo().send_mail(
            self.main_object.id,
            raise_exception=False,
            force_send=True,
            email_values={
                "attachments": [("picture.jpg", picture)],
                "email_to": self.main_object.user_email,
            },
        )
        return True


class OrderMaterialFormFlyer(models.AbstractModel):
    _name = "cms.form.order.material"
    _inherit = "cms.form.order.material.mixin"

    form_id = fields.Char(default="order_material")

    def form_after_create_or_update(self, values, extra_values):
        super(OrderMaterialFormFlyer, self).form_after_create_or_update(
            values, extra_values
        )
        # Attach ambassador picture for flyer creation
        ftype = "jpg"
        partner = self.main_object.partner_id
        image = partner.advocate_details_id.picture_large or partner.image
        mimetype = magic.from_buffer(b64decode(image), True)
        if mimetype and "/" in mimetype:
            ftype = mimetype.split("/")[-1]
        filename = "{}.{}".format(partner.name, ftype)
        uid = self.env.ref("muskathlon.user_muskathlon_portal").id
        self.env["ir.attachment"].sudo(uid).create(
            {
                "res_model": "crm.lead",
                "res_id": self.main_object.id,
                "datas": image,
                "datas_fname": filename,
                "name": filename,
            }
        )


class OrderMaterialFormChildpack(models.AbstractModel):
    _name = "cms.form.order.muskathlon.childpack"
    _inherit = "cms.form.order.material.mixin"

    form_id = fields.Char(default="muskathlon_childpack")
    flyer_number = fields.Selection(string="Number of childpacks")

    def form_before_create_or_update(self, values, extra_values):
        super(OrderMaterialFormChildpack, self).form_before_create_or_update(
            values, extra_values
        )
        values.update(
            {
                "name": "Muskathlon childpack order - {}".format(
                    self.partner_id.name
                ),
                "description": "Number of childpacks wanted: "
                               + extra_values["flyer_number"],
            }
        )
