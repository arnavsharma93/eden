# -*- coding: utf-8 -*-
try:
    # Python 2.7
    from collections import OrderedDict
except:
    # Python 2.6
    from gluon.contrib.simplejson.ordered_dict import OrderedDict

from gluon import current
from gluon.storage import Storage

def config(settings):

    T = current.T
    settings = current.deployment_settings


    settings.base.system_name = T("Sahana Eden Nightly Build Tool")
    settings.base.theme = "default"

    settings.ui.datatables_responsive = False


    # -----------------------------------------------------------------------------
    settings.modules = OrderedDict([
        ("default", Storage(
            name_nice = T("Sahana Eden"),
            restricted = False,
            access = None,
            module_type = None
        )),
        ("admin", Storage(
            name_nice = T("Administration"),
            #description = "Site Administration",
            restricted = True,
            access = "|1|",
            module_type = None
        )),
        ("nightly", Storage(
            name_nice = T("Sahana Eden Nightly Build"),
            restricted = False,
            access = None,
            module_type = None
        ))
    ])
