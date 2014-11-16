# -*- coding: utf-8 -*-

"""
Continuous Integration Tool
"""

module = request.controller
resourcename = request.function

if not settings.has_module(module):
    raise HTTP(404, body="Module disabled: %s" % module)

def index():
    """ Show the index """

    return dict()

# -----------------------------------------------------------------------------
def build():

    from s3 import S3SQLCustomForm, S3SQLInlineComponent, S3SQLInlineLink

    crud_form = S3SQLCustomForm("branch_url",
                                "template",
                                "db_type",
                                "prepop",
                                "tests",
                                "email",
                                )

    s3db.configure("ci_build", crud_form=crud_form)

    def prep(r):
        return True

    s3.prep = prep

    def postp(r, output):
        return output

    s3.postp = postp

    return s3_rest_controller(rheader=s3db.ci_rheader)
