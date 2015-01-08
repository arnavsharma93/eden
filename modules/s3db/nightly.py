# -*- coding: utf-8 -*-

""" Sahana Eden Nightly Model

@copyright: 2015 (c) Sahana Software Foundation
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
__all__ = ("S3NightlyBuildModel",
           "nightly_rheader",
           "nightly_get_templates"
          )

from ..s3 import *
from gluon import *
import os
import socket
import shutil
import time

class S3NightlyBuildModel(S3Model):

    names = ("nightly_build", "nightly_configure")

    def model(self):

        T = current.T
        s3 = current.response.s3
        request = current.request

        define_table = self.define_table
        configure = self.configure
        add_components = self.add_components
        set_method = self.set_method

        tablename = "nightly_build"

        define_table(tablename,
                     Field("date",
                           label = T("Date"),
                           writable = False,
                           readable = True
                           ),
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
                           comment = "Enter list of templates to be tested, comma separated, eg: default, IFRC",
                           required = True
                           # requires = IS_IN_SET(nightly_get_templates(), zero=None),
                           ),
                     Field("db_type",
                           label = T("Database"),
                           default = "mysql, postgres",
                           comment = "Enter the list of databases among \
                                     (mysql, postgres, sqlite3) for each of \
                                     the template given above. Comma delimited \
                                    internally and semi-colon delimited per \
                                     template eg: mysql, postgres; mysql, \
                                     sqlite3",
                           required = True
                           ),
                     Field("prepop",
                           label = T("Pre-populate"),
                           default = "default, default/users",
                           comment = "Enter prepop settings for each of the \
                                     template mentioned above, comma delimited \
                                     internally and semi-colon delimited per \
                                     template. eg: default, default/users; \
                                     IFRC/Train, default/users",
                           required = True,
                           ),
                     Field("max_depth",
                           label = T("Maximum depth"),
                           default = 1,
                           length = 255,
                           ),
                     Field("task_status",
                           label = "Task Status",
                           default = "PENDING",
                           writable = False,
                           readable = True
                           ),
                     Field("build_status",
                           label = "Build Status",
                           default = "UNKNOWN",
                           writable = False,
                           readable = True
                           ),
                     Field("log_file",
                           label = T("Log File"),
                           writable = False,
                           readable = False
                           ),
                     Field("trigger_now", "boolean",
                           label = T("Trigger now"),
                           writable = True,
                           readable = False
                           ),
                     Field("results",
                           writable = False,
                           readable = False
                           ),
                     Field("scheduler_id", "reference scheduler_task",
                           writable = False,
                           readable = False
                           ),

                     *s3_meta_fields()
                    )

        # CRUD Strings
        s3.crud_strings[tablename] = Storage(
            label_create = T("New Build"),
            label_create_button = T("New Build"),
            label_list_button = T("View Builds"),
            label_delete_button = T("Delete Build"),
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
                  deletable = True,
                  insertable = True,
                  listadd = True,
                  onvalidation = build_onvalidation,
                  onaccept = build_onaccept
                  )

        tablename = "nightly_configure"

        define_table(tablename,
                     Field("emails",
                           label = T("Email Notification"),
                           default = "",
                           length = 255,
                           ),
                     Field("subscriptions", "boolean",
                           label = T("Turn subscriptions on/off"),
                           default = False,
                           ),
                     Field("app_name",
                           label = T("Test application name"),
                           comment = "Should be same as the one in the \
                                     uploaded EdenTest config file",
                           default = "eden2",
                           required = True
                           ),
                     Field("psql_db_name",
                           label = T("Postgres: Name of the database"),
                           default = "sahana_temp",
                           required = True
                           ),
                     Field("psql_db_host",
                           label = T("Postgres: Database Host"),
                           default = "localhost"
                           ),
                     Field("psql_db_port",
                           label = T("Postgres: Database Port"),
                           default = "5432",
                           required = True
                           ),
                     Field("psql_db_username",
                           label = T("Postgres: Database username"),
                           default = "arnav",
                           required = True
                           ),
                     Field("psql_db_password",
                           label = T("Postgres: Database Password"),
                           default = "iamarnav",
                           required = True
                           ),
                     Field("mysql_db_name",
                           label = T("MySql: Name of the database"),
                           default = "sahana_temp",
                           required = True
                           ),
                     Field("mysql_db_host",
                           label = T("MySql: Database Host"),
                           default = "localhost"
                           ),
                     Field("mysql_db_port",
                           label = T("MySql: Database Port"),
                           default = "3306",
                           required = True
                           ),
                     Field("mysql_db_username",
                           label = T("MySql: Database username"),
                           default = "root",
                           required = True
                           ),
                     Field("mysql_db_password",
                           label = T("MySql: Database Password"),
                           default = "iiit123",
                           required = True
                           ),
                     Field("edentest_config", "upload",
                           uploadfolder = os.path.join(request.folder,
                                                       "uploads"),
                           label = T("EdenTest Config File"),
                           required = True
                           ),
                     *s3_meta_fields()
                    )

        s3.crud_strings[tablename] = Storage(
            label_create_button = T("Create New Configuration"),
            label_list_button = T("View Configuration"),
            msg_record_created = T("Configuration Created"),
            msg_record_modified = T("Configuration updated"),
            msg_list_empty = T("No Configuration Saved yet"),
            subtitle_create = T("Add Configuration"),
            title_create = T("Add Configuration"),
            title_list = T("View Configuration"),
            title_update = T("Update Configuration"),
        )

        configure(tablename,
                  editable = True
                 )

        return dict()

    def defaults(self):
        """
        Safe defaults for model-global names in case module is disabled
        """
        return dict()

# -----------------------------------------------------------------------------
def nightly_get_templates():
    path = os.path.join(current.request.folder, "private", "templates")
    templates = set(
                    os.path.basename(folder) for folder, subfolders, files in os.walk(path) \
                        for file_ in files if file_ == 'config.py'
                )

    return templates


# -----------------------------------------------------------------------------
def nightly_rheader(r, tabs=[]):
    """ Resource component page header """

    if r.representation == "html":

        T = current.T

        tabs = [(T("Build details"), "nightly_build"),(T("Configuration details"), "nightly_configuration")]

        rheader_tabs = s3_rheader_tabs(r, tabs)

        rheader = DIV(rheader_tabs)

        return rheader

def build_onvalidation(form):
    form_vars = form.vars

    templates = form_vars.get("template").split(",")
    prepops = form_vars.get("prepop").split(";")
    databases = form_vars.get("db_type").split(";")

    if len(templates) != len(databases):
        err_msg = "Number of templates and databases should be same. See help."
        form.errors.template = err_msg
        form.errors.db_type = err_msg
        return

    if len(databases) != len(prepops):
        err_msg = "Number of prepops and databases should be same. See help."
        form.errors.prepop = err_msg
        form.errors.db_type = err_msg
        return

def build_onaccept(form):
    db = current.db
    s3db = current.s3db
    form_vars = form.vars
    request = current.request

    build_table = s3db.nightly_build
    build_row = db(build_table.id == form_vars.id).select(limitby = (0, 1)).first()

    if build_row.trigger_now:
        configure_table = s3db.nightly_configure
        configure_row = db(configure_table.id == 1).select(limitby = (0, 1)).first()

        sctable = db.scheduler_task
        date = time.strftime("%d.%m.%Y.%H.%M.%S")

        build_row.update_record(date=date)

        build_item = {
            "id": build_row.id,
            "repo_url": build_row.repo_url,
            "branch": build_row.branch,
            "template": build_row.template,
            "prepop": build_row.prepop,
            "db_type": build_row.db_type,
            "max_depth": build_row.max_depth,
            "date":build_row.date
        }

        scheduler_id = current.s3task.schedule_task(
            date,
            vars = {
                "build_item": build_item
            },
            function_name = "nightly_build",
            repeats = 1,
            timeout = 3600,
            sync_output = 10
        )

        build_row.update_record(scheduler_id=scheduler_id)


