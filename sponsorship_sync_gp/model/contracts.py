# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

from openerp.osv import orm, fields
from openerp.tools.translate import _
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DF

from sponsorship_compassion.model.product import GIFT_TYPES
from datetime import datetime
from dateutil.relativedelta import relativedelta

from . import gp_connector


class contracts(orm.Model):
    _inherit = 'recurring.contract'

    def create(self, cr, uid, vals, context=None):
        """ When contract is created, push it to GP so that the mailing
        module can access all information. """
        contract_id = super(contracts, self).create(cr, uid, vals, context)
        gp_connect = gp_connector.GPConnect(cr, uid)
        contract = self.browse(cr, uid, contract_id, context)
        # Check that the contract is compatible with GP
        # (= only sponsorship and/or fund products, nothing else)
        if self._is_gp_compatible(contract):
            if not gp_connect.create_or_update_contract(uid, contract):
                raise orm.except_orm(
                    _("GP Sync Error"),
                    _("Please contact an IT person."))
        else:
            raise orm.except_orm(
                _("Not compatible with GP"),
                _("You selected some products that are not available in GP."),
                _("You cannot create this contract.")
            )
        return contract_id

    def write(self, cr, uid, ids, vals, context=None):
        """ Keep GP updated when a contract is modified. """
        gp_connect = gp_connector.GPConnect(cr, uid)
        ids = [ids] if not isinstance(ids, list) else ids

        # If we change the next invoice date, it means we cancel
        # invoices generation and should thus update the situation
        # in GP (advance the months paid).
        if vals.get('next_invoice_date'):
            new_date = datetime.strptime(vals['next_invoice_date'], DF)
            for contract in self.browse(cr, uid, ids, context=context):
                old_date = datetime.strptime(contract.next_invoice_date, DF)
                month_diff = relativedelta(new_date, old_date).months
                if contract.state in ('active', 'waiting') and month_diff > 0:
                    if not gp_connect.register_payment(contract.id,
                                                       amount=month_diff):
                        raise orm.except_orm(
                            _("GP Sync Error"),
                            _("Please contact an IT person."))

        res = super(contracts, self).write(cr, uid, ids, vals, context)
        for contract in self.browse(cr, uid, ids, context):
            if self._is_gp_compatible(contract):
                if not gp_connect.create_or_update_contract(uid, contract):
                    raise orm.except_orm(
                        _("GP Sync Error"),
                        _("Please contact an IT person."))
            else:
                raise orm.except_orm(
                    _("Not compatible with GP"),
                    _("You selected some products that are not available "
                      "in GP."),
                    _("You cannot save this contract."))

        return res

    def _is_gp_compatible(self, contract):
        """ Tells if the contract is compatible with GP. """
        compatible = True
        for line in contract.contract_line_ids:
            compatible = compatible and (
                _('Sponsorship') in line.product_id.name
                or line.product_id.gp_fund_id > 0)
        return compatible

    def contract_waiting(self, cr, uid, ids, context=None):
        """ When contract is validated, calculate which month is due
        and push it to GP.
        """
        super(contracts, self).contract_waiting(cr, uid, ids, context)
        gp_connect = gp_connector.GPConnect(cr, uid)
        for contract in self.browse(cr, uid, ids, context):
            if not gp_connect.validate_contract(contract):
                raise orm.except_orm(
                    _("GP Sync Error"),
                    _("The contract could not be validated."),
                    _("Please contact an IT person."))
        return True

    def contract_cancelled(self, cr, uid, ids, context=None):
        """ When contract is cancelled, update it in GP. """
        super(contracts, self).contract_cancelled(cr, uid, ids, context)
        gp_connect = gp_connector.GPConnect(cr, uid)
        for contract in self.browse(cr, uid, ids, context):
            if not gp_connect.finish_contract(contract):
                raise orm.except_orm(
                        _("GP Sync Error"),
                        _("Please contact an IT person."))
        return True

    def contract_terminated(self, cr, uid, ids, context=None):
        """ When contract is terminated, update it in GP. """
        super(contracts, self).contract_terminated(cr, uid, ids)
        gp_connect = gp_connector.GPConnect(cr, uid)
        for contract in self.browse(cr, uid, ids, context):
            if not gp_connect.finish_contract(contract):
                raise orm.except_orm(
                    _("GP Sync Error"),
                    _("The contract could not be terminated."),
                    _("Please contact an IT person."))
        return True

    def _on_contract_active(self, cr, uid, ids, context=None):
        """ When contract is active, update it in GP. """
        super(contracts, self)._on_contract_active(cr, uid, ids, context)
        gp_connect = gp_connector.GPConnect(cr, uid)
        for contract in self.browse(cr, uid, ids, context):
            if not gp_connect.activate_contract(contract):
                raise orm.except_orm(
                    _("GP Sync Error"),
                    _("The contract could not be activated."),
                    _("Please contact an IT person."))

    def _invoice_paid(self, cr, uid, invoice, context=None):
        """ When a customer invoice is paid, synchronize GP. """
        super(contracts, self)._invoice_paid(cr, uid, invoice, context)
        if invoice.type == 'out_invoice':
            gp_connect = gp_connector.GPConnect(cr, uid)
            last_pay_date = max([move_line.date
                                 for move_line in invoice.payment_ids
                                 if move_line.credit > 0] or [False])
            contract_ids = set()
            for line in invoice.invoice_line:
                if last_pay_date:
                    gp_connect.insert_affectat(uid, line, last_pay_date)
                else:   # Invoice will go back in open state
                    gp_connect.remove_affectat(invoice.id, line.due_date)
                contract = line.contract_id
                if contract:
                    to_update = (line.product_id.name not in
                                 GIFT_TYPES) and (contract.id
                                                               not in
                                                               contract_ids)
                    if last_pay_date and to_update:
                        contract_ids.add(contract.id)
                        if not gp_connect.register_payment(contract.id,
                                                           last_pay_date):
                            raise orm.except_orm(
                                _("GP Sync Error"),
                                _("The payment could not be registered into "
                                  "GP."),
                                _("Please contact an IT person."))
                    elif to_update:
                        contract_ids.add(contract.id)
                        if not gp_connect.undo_payment(contract.id):
                            raise orm.except_orm(
                                _("GP Sync Error"),
                                _("The payment could not be removed from GP."),
                                _("Please contact an IT person."))


class contract_group(orm.Model):

    """ Update all contracts when group is changed. """
    _inherit = 'recurring.contract.group'

    def write(self, cr, uid, ids, vals, context=None):
        res = super(contract_group, self).write(cr, uid, ids, vals, context)
        gp_connect = gp_connector.GPConnect(cr, uid)
        for group in self.browse(cr, uid, ids, context):
            for contract in group.contract_ids:
                if not gp_connect.create_or_update_contract(uid, contract):
                    raise orm.except_orm(
                        _("GP Sync Error"),
                        _("Please contact an IT person."))
        return res
