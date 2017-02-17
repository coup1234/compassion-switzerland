# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Stephane Eicher <eicher31@hotmail.com>
#
#    The licence is in the file __openerp__.py
#
##############################################################################
import sys
import base64

from io import BytesIO
from openerp.exceptions import Warning

from . import translate_connector

from openerp import models, api, _
from openerp.tools.config import config
from openerp.addons.sbc_compassion.models.correspondence_page import \
    BOX_SEPARATOR

from smb.SMBConnection import SMBConnection

import logging
logger = logging.getLogger(__name__)


class Correspondence(models.Model):
    """ This class intercepts a letter before it is sent to GMC.
        Letters are pushed to local translation platform if needed.
        """

    _inherit = 'correspondence'

    ##########################################################################
    #                              ORM METHODS                               #
    ##########################################################################
    @api.model
    def create(self, vals):
        """ Create a message for sending the CommKit after be translated on
             the local translate plaform.
        """
        if vals.get('direction') == "Beneficiary To Supporter":
            correspondence = super(Correspondence, self).create(vals)
        else:
            sponsorship = self.env['recurring.contract'].browse(
                vals['sponsorship_id'])

            original_lang = self.env['res.lang.compassion'].browse(
                vals.get('original_language_id'))

            # TODO Remove this fix when HAITI case is resolved
            # For now, we switch French to Creole for avoiding translation
            if 'HA' in sponsorship.child_id.local_id:
                french = self.env.ref(
                    'child_compassion.lang_compassion_french')
                creole = self.env.ref(
                    'child_compassion.lang_compassion_haitien_creole')
                if original_lang == french:
                    vals['original_language_id'] = creole.id

            if original_lang.translatable and original_lang not in sponsorship\
                    .child_id.project_id.field_office_id.spoken_language_ids:
                correspondence = super(Correspondence, self.with_context(
                    no_comm_kit=True)).create(vals)
                correspondence.send_local_translate()
            else:
                correspondence = super(Correspondence, self).create(vals)

        return correspondence

    ##########################################################################
    #                             PUBLIC METHODS                             #
    ##########################################################################
    @api.multi
    def process_letter(self):
        """ Called when B2S letter is Published. Check if translation is
         needed and upload to translation platform. """
        letters_to_send = self.env[self._name]
        for letter in self:
            # if letter.original_language_id in \
            #         letter.supporter_languages_ids or \
            if (letter.beneficiary_language_ids &
                    letter.supporter_languages_ids) or \
                    letter.has_valid_language:
                if super(Correspondence, letter).process_letter():
                    letters_to_send += letter
            else:
                letter.download_attach_letter_image()
                letter.send_local_translate()

        letters_to_send.send_communication()
        return True

    @api.one
    def send_local_translate(self):
        """
        Sends the letter to the local translation platform.
        :return: None
        """
        child = self.sponsorship_id.child_id

        # Specify the src and dst language
        src_lang_id, dst_lang_id = self._get_translation_langs()

        # File name
        sponsor = self.sponsorship_id.partner_id
        # TODO : replace by global_id once all ids are fetched
        file_name = "_".join(
            (child.local_id, sponsor.ref, str(self.id))) + '.pdf'

        # Send letter to local translate platform
        tc = translate_connector.TranslateConnect()
        text_id = tc.upsert_text(
            self, file_name, tc.get_lang_id(src_lang_id),
            tc.get_lang_id(dst_lang_id))
        translation_id = tc.upsert_translation(text_id, self)
        tc.upsert_translation_status(translation_id)

        # Transfer file on the NAS
        self._transfer_file_on_nas(file_name)
        self.state = 'Global Partner translation queue'

    @api.one
    def remove_local_translate(self):
        """
        Remove a letter from local translation platform and change state of
        letter in Odoo
        :return: None
        """
        tc = translate_connector.TranslateConnect()
        tc.remove_translation_with_odoo_id(self.id)
        if self.direction == 'Supporter To Beneficiary':
            self.state = 'Received in the system'
            self.create_commkit()
        else:
            self.state = 'Published to Global Partner'

    @api.one
    def update_translation(self, translate_lang, translate_text, translator):
        """
        Puts the translated text into the correspondence.
        :param translate_lang: code_iso of the language of the translation
        :param translate_text: text of the translation
        :return: None
        """
        translate_lang_id = self.env['res.lang.compassion'].search(
            [('code_iso', '=', translate_lang)]).id
        translator_partner = self.env['res.partner'].search([
            ('ref', '=', translator)])

        if self.direction == 'Supporter To Beneficiary':
            state = 'Received in the system'
            target_text = 'original_text'
            language_field = 'original_language_id'
            # Remove #BOX# in the text, as supporter letters don't have boxes
            translate_text = translate_text.replace(BOX_SEPARATOR, '\n')
            # TODO Remove this fix when HAITI case is resolved
            # For now we switch French to Creole
            if 'HA' in self.child_id.local_id:
                french = self.env.ref(
                    'child_compassion.lang_compassion_french')
                creole = self.env.ref(
                    'child_compassion.lang_compassion_haitien_creole')
                if translate_lang_id == french.id:
                    translate_lang_id = creole.id
        else:
            state = 'Published to Global Partner'
            target_text = 'translated_text'
            language_field = 'translation_language_id'
            # TODO Remove this when new translation tool is working
            # Workaround to avoid overlapping translation : everything goes
            # in L6 template
            self.b2s_layout_id = self.env.ref('sbc_compassion.b2s_l6')

        # Check that layout L4 translation gets on second page
        if self.b2s_layout_id == self.env.ref('sbc_compassion.b2s_l4') and \
                not translate_text.startswith('#PAGE#'):
            translate_text = '#PAGE#' + translate_text
        self.write({
            target_text: translate_text.replace('\r', ''),
            'state': state,
            language_field: translate_lang_id,
            'translator_id': translator_partner.id})

        # Send to GMC
        if self.direction == 'Supporter To Beneficiary':
            self.create_commkit()
        else:
            # Recompose the letter image and process letter
            self.letter_image.unlink()
            if super(Correspondence, self).process_letter():
                self.send_communication()

    ##########################################################################
    #                             PRIVATE METHODS                            #
    ##########################################################################
    def _get_translation_langs(self):
        """
        Finds the source_language et destination_language suited for
        translation of the given letter.

        S2B:
            - src_lang is the original language of the letter
            - dst_lang is the lang of the child if translatable, else
              english

        B2S:
            - src_lang is the original language if translatable, else
              english
            - dst_lang is the main language of the sponsor
        :return: src_lang, dst_lang
        :rtype: res.lang.compassion, res.lang.compassion
        """
        self.ensure_one()
        src_lang_id = False
        dst_lang_id = False
        if self.direction == 'Supporter To Beneficiary':
            # Check that the letter is not yet sent to GMC
            if self.kit_identifier:
                raise Warning(_("Letter already sent to GMC cannot be "
                                "translated! [%s]") % self.kit_identifier)

            src_lang_id = self.original_language_id
            child_langs = self.beneficiary_language_ids.filtered(
                'translatable')
            if child_langs:
                dst_lang_id = child_langs[-1]
            else:
                dst_lang_id = self.env.ref(
                    'child_compassion.lang_compassion_english')

        elif self.direction == 'Beneficiary To Supporter':
            if self.original_language_id and \
                    self.original_language_id.translatable:
                src_lang_id = self.original_language_id
            else:
                src_lang_id = self.env.ref(
                    'child_compassion.lang_compassion_english')
            dst_lang_id = self.supporter_languages_ids.filtered(
                lambda lang: lang.lang_id and lang.lang_id.code ==
                self.correspondant_id.lang)

        return src_lang_id, dst_lang_id

    def _transfer_file_on_nas(self, file_name):
        """
        Puts the letter file on the NAS folder for the translation platform.
        :return: None
        """
        self.ensure_one()
        # Retrieve configuration
        smb_user = config.get('smb_user')
        smb_pass = config.get('smb_pwd')
        smb_ip = config.get('smb_ip')
        smb_port = int(config.get('smb_port', 0))
        if not (smb_user and smb_pass and smb_ip and smb_port):
            raise Exception('No config SMB in file .conf')

        # Copy file in the imported letter folder
        smb_conn = SMBConnection(smb_user, smb_pass, 'openerp', 'nas')
        if smb_conn.connect(smb_ip, smb_port):
            file_ = BytesIO(base64.b64decode(
                self.letter_image.with_context(
                    bin_size=False).datas))
            nas_share_name = self.env.ref(
                'sbc_switzerland.nas_share_name').value

            nas_letters_store_path = self.env.ref(
                'sbc_switzerland.nas_letters_store_path').value + file_name
            smb_conn.storeFile(nas_share_name,
                               nas_letters_store_path, file_)

            logger.info('File {} store on NAS with success'
                        .format(self.letter_image.name))
        else:
            raise Warning(_('Connection to NAS failed'))

    # CRON Methods
    ##############
    @api.model
    def check_local_translation_done(self):
        reload(sys)
        sys.setdefaultencoding('UTF8')
        tc = translate_connector.TranslateConnect()
        letters_to_update = tc.get_translated_letters()

        for letter in letters_to_update:
            correspondence = self.browse(letter["letter_odoo_id"])
            logger.info(".....CHECK TRANSLATION FOR LETTER {}".format(
                correspondence.id))
            if not correspondence.exists():
                logger.warning(("The correspondence id {} doesn't exist in the"
                                "Odoo DB. Remove it manually on MySQL DB. \
                                'todo_id' is set to 5 => 'Pas sur Odoo'")
                               .format(correspondence.id))
                tc.update_translation_to_not_in_odoo(letter["id"])
                continue

            correspondence.update_translation(letter["target_lang"],
                                              letter["text"],
                                              letter["translator"])
            # tc.remove_letter(letter["text_id"])
            # update: don't remove letter but set todo id to 'Traité'
            tc.update_translation_to_treated(letter["id"])
            self.env.cr.commit()
        return True
