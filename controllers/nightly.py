# -*- coding: utf-8 -*-

"""
Nightly Build Tool
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

    from s3 import S3SQLCustomForm

    crud_form = S3SQLCustomForm("repo_url",
                                "branch",
                                "template",
                                "db_type",
                                "prepop",
                                "max_depth",
                                "scheduler_id",
                                "trigger_now"
                                )

    s3db.configure("nightly_build", crud_form=crud_form)

    def prep(r):
        configure_table = s3db.nightly_configure

        if db(configure_table).isempty():
            s3db.configure("nightly_build",
                           insertable = False
                          )
            response.error = "Create Configuration first"


        update_color = """
            $(document).ready(function() {
                var table = $("#datatable");
                table.find('tr').each(function (i, el) {
                    var $cells = $(this).find('td');
                    switch($cells.eq(8).text())
                    {
                        case "COMPLETED":
                            if($cells.eq(9).text() != "PASS")
                            {
                                $(this).addClass("failed");
                            }
                            else
                            {
                                $(this).addClass("completed");
                            }
                            break;

                        case "FAILED":
                            $(this).addClass("failed");
                            break;

                        case "QUEUED":
                            $(this).addClass("queued");
                            break;

                        case "ASSIGNED":
                            $(this).addClass("assigned");
                            break;

                        case "RUNNING":
                            $(this).addClass("running");
                            break;

                        default:
                            break;
                    }
                });
                table.find('th').each(function (i, el) {
                    $(this).removeClass();
                    $(this).addClass("sorting_disabled");
                });

            });
        """
        s3.js_global.append(update_color)


        build_table = s3db.nightly_build
        sctable = db.scheduler_task


        query = (build_table.task_status != "FAILED") & (build_table.task_status != "COMPLETED")
        rows = db(query).select()

        for row in rows:
            if row.scheduler_id:

                query = (row.scheduler_id == sctable.id)
                sc_row = db(query).select().first()
                task_status = sc_row.status

                if task_status not in ("COMPLETED", "FAILED"):
                    row.update_record(task_status=task_status,
                                      build_status="BUILDING"
                                     )
                elif task_status == "FAILED":
                    row.update_record(task_status=task_status,
                                      build_status="ERROR"
                                     )

                row.update_record(task_status=task_status)

        return True

    s3.prep = prep

    def postp(r, output):

        s3.stylesheets.append("S3/nightly.css")

        if r.method in (None, "read") and r.id:

            # get scheduler status for the last queued task
            build_table = s3db.nightly_build
            sctable = db.scheduler_task

            query = (build_table.id == r.id)
            sc_row = db(query).select(sctable.id,
                                   sctable.status,
                                   join = build_table.on(build_table.scheduler_id==sctable.id),
                                   orderby = build_table.scheduler_id
                                   ).last()


            item_append = output["item"][0].append
            build_row = db(query).select().first()
            log_file = build_row.log_file
            results = []
            if build_row.results:
                results = eval(build_row.results)

            if sc_row and sc_row.status == "FAILED":

                resource = s3db.resource("scheduler_run")
                task = db(resource.table.task_id == sc_row.id).select().first()

                item_append(TR(TD(LABEL("Traceback", _class="label_class"), _class="w2p_fl")))
                traceback = task.traceback

                item_append(TR(TD(PRE(traceback))))

            item_append(TR(TD(LABEL("Logs", _class="label_class"), _class="w2p_fl")))


            link_log_file = "%s://%s/%s/%s" % (request.env.wsgi_url_scheme,
                                               request.env.http_host,
                                               request.application,
                                               log_file
                                              )
            item_append(TR(TD(A('Logs', _href=link_log_file))))

            item_append(TR(TD(LABEL("Results", _class="label_class"), _class="w2p_fl")))

            for result in results:
                print result
                result_file = result[0]
                rc = int(result[1])


                link_result_file = "%s://%s/%s/%s" % (request.env.wsgi_url_scheme,
                                                      request.env.http_host,
                                                      request.application,
                                                      result_file
                                                     )
                filename = result_file.split('/')[-1]

                if rc == 0:
                    status = "PASS"
                elif rc < 251:
                    status = "FAIL"
                else:
                    status = "ERROR"

                item_append(TR(TD(A("%s %s" % (status, filename), XML('<br>'), _href=link_result_file))))

        return output

    s3.postp = postp
    return s3_rest_controller(rheader=s3db.nightly_rheader)


def configure():

    from s3 import S3SQLCustomForm
    s3db = current.s3db

    configure_table = s3db.nightly_configure

    insertable = False

    if db(configure_table).isempty():
        insertable = True


    crud_form = S3SQLCustomForm("emails",
                                "subscriptions",
                                "app_name",
                                "psql_db_name",
                                "psql_db_host",
                                "psql_db_port",
                                "psql_db_username",
                                "psql_db_password",
                                "mysql_db_name",
                                "mysql_db_host",
                                "mysql_db_port",
                                "mysql_db_username",
                                "mysql_db_password",
                                "edentest_config"
                                )

    s3db.configure("nightly_configure", crud_form=crud_form, insertable=insertable)

    def prep(r):
        return True

    s3.prep = prep

    def postp(r, output):
        return output

    s3.postp = postp

    return s3_rest_controller(rheader=s3db.nightly_rheader)
