# -*- coding: utf-8 -*-

""" Sahana Eden CI Model

@copyright: 2014 (c) Sahana Software Foundation
@license: MIT

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.
"""
__all__ = ("S3CIBuildModel",
           "ci_rheader",
           "ci_get_templates"
          )

from ..s3 import *
from gluon import *
import os
import socket
import shutil
import time

class S3CIBuildModel(S3Model):

    names = ("ci_build")

    def model(self):

        T = current.T
        s3 = current.response.s3

        define_table = self.define_table
        configure = self.configure
        add_components = self.add_components
        set_method = self.set_method

        tablename = "ci_build"

        define_table(tablename,
                     Field("repo_url",
                           label = T("Eden repo git URL"),
                           default = "https://github.com/flavour/eden",
                           required = True,
                           ),
                     Field("branch",
                           label = T("Branch"),
                           default = "master",
                           required = True,
                           ),
                     Field("template",
                           label = T("Template"),
                           default = "default",
                           requires = IS_IN_SET(ci_get_templates(), zero=None),
                           ),
                     Field("db_type", "integer",
                           label = T("Database"),
                           default = "sqlite3",
                           requires = IS_IN_SET({1:"mysql", 2: "postgresql"}),
                           ),
                     Field("prepop",
                           label = T("Pre-populate"),
                           default = ("default", "default/users"),
                           required = True,
                           ),
                     Field("tests",
                           label = T("Tests"),
                           default = "*",
                           required = True,
                           ),
                     Field("email",
                           label = T("Email Notification"),
                           default = "",
                           length = 255,
                           ),
                     Field("scheduler_id", "reference scheduler_task",
                           writable = False,
                           readable = False
                          ),
                     *s3_meta_fields()
                    )

        # CRUD Strings
        s3.crud_strings[tablename] = Storage(
            label_create_button = T("New Build"),
            label_list_button = T("View Builds"),
            label_delete_button = T("Delete Deployment"),
            msg_record_created = T("Build Created"),
            msg_record_modified = T("Build updated"),
            msg_record_deleted = T("Build deleted"),
            msg_list_empty = T("No Build Saved yet"),
            subtitle_create = T("Add Build"),
            title_create = T("Add Build"),
            title_list = T("View Builds"),
            title_update = T("Edit Build"),
        )

        configure(tablename,
                  editable = False,
                  deletable = False,
                  insertable = True,
                  listadd = True,
                  onaccept = build_onaccept
                  )


    def defaults(self):
        """
        Safe defaults for model-global names in case module is disabled
        """
        return dict()

# -----------------------------------------------------------------------------
def ci_get_templates():
    path = os.path.join(current.request.folder, "private", "templates")
    templates = set(
                    os.path.basename(folder) for folder, subfolders, files in os.walk(path) \
                        for file_ in files if file_ == 'config.py'
                )

    return templates


# -----------------------------------------------------------------------------
def ci_rheader(r, tabs=[]):
    """ Resource component page header """

    if r.representation == "html":

        T = current.T

        tabs = [(T("Build details"), None)]

        rheader_tabs = s3_rheader_tabs(r, tabs)

        rheader = DIV(rheader_tabs)

        return rheader

def build_onaccept(form):
    db = current.db
    s3db = current.s3db
    form_vars = form.vars

    ci_table = s3db.ci_build

    item = db(ci_table.id == form_vars.id).select(limitby = (0, 1)).first()

    name = "branch_%s_%s" % (item.repo_url, item.branch)

    row = current.s3task.schedule_task(
        name,
        vars = {
            "repo_url": item.repo_url,
            "branch": item.branch,
            "template": item.template,
            "prepop": item.prepop,
            "db_type": item.db_type,
            "tests": item.tests
        },
        function_name = "ci_build",
        repeats = 1,
        timeout = 3600,
        sync_output = 10
    )


    item.update_record(scheduler_id=row)
