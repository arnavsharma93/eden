# -*- coding: utf-8 -*-

# =============================================================================
# Tasks to be callable async
# =============================================================================

tasks = {}

# -----------------------------------------------------------------------------
def maintenance(period="daily"):
    """
        Run all maintenance tasks which should be done daily
        - these are read from the template
    """

    mod = "applications.%s.private.templates.%s.maintenance as maintenance" % \
                    (appname, settings.get_template())
    try:
        exec("import %s" % mod)
    except ImportError, e:
        # No Custom Maintenance available, use the default
        exec("import applications.%s.private.templates.default.maintenance as maintenance" % appname)

    if period == "daily":
        result = maintenance.Daily()()
    else:
        result = "NotImplementedError"

    db.commit()
    return result

tasks["maintenance"] = maintenance

# -----------------------------------------------------------------------------
if settings.has_module("doc"):

    # -----------------------------------------------------------------------------
    def document_create_index(document, user_id=None):

        import os
        from xlrd import open_workbook
        from pyth.plugins.rtf15.reader import Rtf15Reader
        from pyth.plugins.plaintext.writer import PlaintextWriter
        import sunburnt

        document = json.loads(document)
        table = s3db.doc_document
        id = document["id"]

        name = document["name"]
        filename = document["filename"]

        filename = "%s/%s/uploads/%s" % (os.path.abspath("applications"), \
                                        request.application, filename)

        si = sunburnt.SolrInterface(settings.get_base_solr_url())

        extension = os.path.splitext(filename)[1][1:]

        if extension == "pdf":
            data = os.popen("pdf2txt.py " + filename).read()
        elif extension == "doc":
            data = os.popen("antiword " + filename).read()
        elif extension == "xls":
            wb = open_workbook(filename)
            data=" "
            for s in wb.sheets():
                for row in range(s.nrows):
                    values = []
                    for col in range(s.ncols):
                        values.append(str(s.cell(row, col).value))
                    data = data + ",".join(values) + "\n"
        elif extension == "rtf":
            doct = Rtf15Reader.read(open(filename))
            data = PlaintextWriter.write(doct).getvalue()
        else:
            data = os.popen("strings " + filename).read()

        # The text needs to be in unicode or ascii, with no contol characters
        data = str(unicode(data, errors="ignore"))
        data = "".join(c if ord(c) >= 32 else " " for c in data)

        # Put the data according to the Multiple Fields
        # @ToDo: Also, would change this according to requirement of Eden
        document = {"id": str(id), # doc_document.id
                    "name": data, # the data of the file
                    "url": filename, # the encoded file name stored in uploads/
                    "filename": name, # the filename actually uploaded by the user
                    "filetype": extension  # x.pdf -> pdf is the extension of the file
                    }

        # Add and commit Indices
        si.add(document)
        si.commit()
        # After Indexing, set the value for has_been_indexed to True in the database
        db(table.id == id).update(has_been_indexed = True)

        db.commit()

    tasks["document_create_index"] = document_create_index

    # -----------------------------------------------------------------------------
    def document_delete_index(document, user_id=None):

        import sunburnt

        document = json.loads(document)
        table = s3db.doc_document
        id = document["id"]
        filename = document["filename"]

        si = sunburnt.SolrInterface(settings.get_base_solr_url())

        # Delete and Commit the indicies of the deleted document
        si.delete(id)
        si.commit()
        # After removing the index, set has_been_indexed value to False in the database
        db(table.id == id).update(has_been_indexed = False)

        db.commit()

    tasks["document_delete_index"] = document_delete_index

# -----------------------------------------------------------------------------
def gis_download_kml(record_id, filename, session_id_name, session_id,
                     user_id=None):
    """
        Download a KML file
            - will normally be done Asynchronously if there is a worker alive

        @param record_id: id of the record in db.gis_layer_kml
        @param filename: name to save the file as
        @param session_id_name: name of the session
        @param session_id: id of the session
        @param user_id: calling request's auth.user.id or None
    """
    if user_id:
        # Authenticate
        auth.s3_impersonate(user_id)
    # Run the Task & return the result
    result = gis.download_kml(record_id, filename, session_id_name, session_id)
    db.commit()
    return result

tasks["gis_download_kml"] = gis_download_kml

# -----------------------------------------------------------------------------
def gis_update_location_tree(feature, user_id=None):
    """
        Update the Location Tree for a feature
            - will normally be done Asynchronously if there is a worker alive

        @param feature: the feature (in JSON format)
        @param user_id: calling request's auth.user.id or None
    """
    if user_id:
        # Authenticate
        auth.s3_impersonate(user_id)
    # Run the Task & return the result
    feature = json.loads(feature)
    path = gis.update_location_tree(feature)
    db.commit()
    return path

tasks["gis_update_location_tree"] = gis_update_location_tree
# -----------------------------------------------------------------------------

if settings.has_module("nightly"):
    import subprocess
    import os
    import shutil
    import errno
    import re
    import sys
    import time

    def nightly_build(build_item, user_id=None):

        # def run_process(name, *args):
        #     sys.stdout.write("Running command %s" % ' '.join(list(args)))
        #     exec_status = subprocess.check_call(list(args))

        #     if not exec_status:
        #         return exec_status
        #     else:
        #         raise Exception("%s is not working as expected" % name)


        def make_header(header):
            len_header = len(header)
            len_dlm = 78 - len_header
            dlm = "=" * (len_dlm/2)

            return "\n%s %s %s\n" % (dlm, header, dlm)

        def run_process(name, *args):

            command = " ".join(args)

            log_file.write(make_header(name))

            log_file.write("%s\n" % command)

            process = subprocess.Popen(list(args),
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE
                                      )
            stdout, stderr = process.communicate()

            log_file.write("STDOUT\n")
            if stdout:
                log_file.write("%s\n" % stdout)

            log_file.write("STDERR\n")
            if stderr:
                log_file.write("%s\n" % stderr)

            return process.returncode

        def create_sub_build(template, db_type, prepop):

            name = "PARAMS"
            log_file.write(make_header(name))

            params = "\n template - %s\n Database - %s\n Prepop - %s\n\n" %\
                    (template, db_type, prepop)

            log_file.write(params)


            name = "Copying Config file"
            log_file.write(make_header(name))

            src = os.path.join(location, "private", "templates", "000_config.py")
            dst = os.path.join(location, "models", "000_config.py")

            # create config file
            shutil.copyfile(src, dst)

            # remove and create a new database
            # mysql
            if db_type == "mysql":
                db_host = configure_item["mysql_db_host"]
                db_port = configure_item["mysql_db_port"]
                db_name = configure_item["mysql_db_name"]
                db_password = configure_item["mysql_db_password"]
                db_username = configure_item["mysql_db_username"]
                os.environ["PGPASSWORD"] = db_password

                run_process("drop pre-existing database",
                            "mysql",
                            "-h",
                            db_host,
                            "-P",
                            db_port,
                            "-u",
                            db_username,
                            "-p%s" % db_password,
                            "-e",
                            "DROP DATABASE IF EXISTS %s;" % db_name
                            )
                run_process("create a new database",
                            "mysql",
                            "-h",
                            db_host,
                            "-P",
                            db_port,
                            "-u",
                            db_username,
                            "-p%s" % db_password,
                            "-e",
                            "CREATE DATABASE %s;" % db_name
                            )

            # postgres
            elif db_type == "postgres":
                db_host = configure_item["psql_db_host"]
                db_port = configure_item["psql_db_port"]
                db_name = configure_item["psql_db_name"]
                db_password = configure_item["psql_db_password"]
                db_username = configure_item["psql_db_username"]


                output = subprocess.check_output("psql --version", shell=True).split()

                version = None

                for word in output:
                    try:
                        digit = int(word[0])
                        digits = word.split(".")
                        version = ".".join(digits[0:2])
                        version = float(version)
                        break
                    except:
                        continue

                name = "psql version %f" % (version)
                log_file.write(make_header(name))

                if version > 9.1:
                    pid = "pid"
                else:
                    pid = "procpid"

                # terminate active connections query
                terminate_conn = ("SELECT "
                                  "pg_terminate_backend(pg_stat_activity.%s) "
                                  "FROM "
                                  "pg_stat_activity "
                                  "WHERE "
                                  "pg_stat_activity.datname = '%s' "
                                  "AND %s <> pg_backend_pid();"
                                 ) % (pid, db_name, pid)

                run_process("dropping connections",
                            "psql",
                            "-U",
                            db_username,
                            "-c",
                            terminate_conn
                           )

                # remove database
                run_process("dropping database",
                            "psql",
                            "-U",
                            db_username,
                            "-c",
                            "DROP DATABASE IF EXISTS %s;" % db_name
                           )

                run_process("create a new database",
                            "psql",
                            "-U",
                            db_username,
                            "-c",
                            "CREATE DATABASE %s;" % db_name
                            )


            try:
                database_folder = os.path.join(location, "databases")

                for f in os.listdir(database_folder):
                    file_path = os.path.join(database_folder, f)
                    os.remove(file_path)
            except:
                pass

            name = "Creating config file"
            log_file.write(make_header(name))

            # read src file
            with open(src, "r") as config_file:
                lines = config_file.readlines()

            # write to the destination
            with open(dst, "w") as cfile:
                for line in lines:
                    # remove trailing spaces
                    line = line.rstrip()

                    line = re.sub("EDITING_CONFIG_FILE = False",
                                  "EDITING_CONFIG_FILE = True",
                                  line
                                 )

                    line = re.sub('settings.base.template = "default"',
                                  'settings.base.template = "%s"' % template,
                                  line
                                  )

                    line = re.sub('#settings.database.db_type = "%s"' % db_type,
                                  'settings.database.db_type = "%s"' % db_type,
                                  line
                                 )


                    line = re.sub('#settings.database.host = "localhost"',
                                  'settings.database.host = "%s"' % db_host,
                                  line
                                 )

                    line = re.sub("#settings.database.port = 3306",
                                  "settings.database.port = %s" % db_port,
                                  line
                                 )

                    line = re.sub('#settings.database.database = "sahana"',
                                  'settings.database.database = "%s"' % db_name,
                                  line
                                 )

                    line = re.sub('#settings.database.password = "password"',
                                  'settings.database.password = "%s"' % db_password,
                                  line
                                 )

                    line = re.sub('#settings.database.username = "sahana"',
                                  'settings.database.username = "%s"' % db_username,
                                  line
                                 )

                    line = re.sub('#settings.base.prepopulate = \("default", "default/users"\)',
                                  "settings.base.prepopulate = %s" % prepop,
                                  line
                                 )

                    line = re.sub("#settings.ui.navigate_away_confirm = False",
                                  "settings.ui.navigate_away_confirm = False",
                                  line
                                 )


                    line = re.sub("settings.base.debug = False",
                                  "settings.base.debug = True",
                                  line
                                 )

                    cfile.write("%s\n" % line)

            # prepop
            name = "Prepop"
            log_file.write(make_header(name))

            os.chdir(web2py_folder)

            run_process("prepop",
                        "python",
                        "web2py.py",
                        "-S",
                        app_name,
                        "-M",
                        "-R",
                        "applications/%s/static/scripts/tools/noop.py" % app_name
                        )

            name = "Copying EdenTest Config file"
            log_file.write(make_header(name))

            runner_file = os.path.join("applications", app_name, "tests", "edentest_runner.py")

            dst = os.path.join(location, "tests", "execution", "settings", "config.py")

            # create config file
            shutil.copyfile(edentest_config, dst)

            name = "Running Tests"
            log_file.write(make_header(name))

            # "python web2py.py --no-banner -M -S eden  -R applications/eden/tests/edentest_runner.py -A  smoke_tests  -o NONE -l NONE"
            filename = "%s_%s.txt" % (template, db_type)

            filepath = os.path.join(abs_results_folder, filename)

            rel_filepath = os.path.join(results_folder, filename)
            results = db(table.id == build_id).select().first().results


            rc = run_process("run tests",
                             "python",
                             "web2py.py",
                             "--no-banner",
                             "-M",
                             "-S",
                             app_name,
                             "-R",
                             runner_file,
                             "-A",
                             "smoke_tests",
                             "-o",
                             "NONE",
                             "-l",
                             "NONE",
                             "-v",
                             "filename:%s" % filepath,
                             "-v",
                             "MAXDEPTH:%s" % max_depth
                            )

            if not results:
                db(table.id == build_id).update(results="[('%s','%d')]" %\
                                                        (rel_filepath, rc))
            else:
                results_list = eval(results)
                results_list.append((rel_filepath, rc))
                results = str(results_list)
                db(table.id == build_id).update(results=results)

            db.commit()

            return rc


        table = s3db.nightly_build


        repo_url = build_item["repo_url"]
        branch = build_item["branch"]
        templates = build_item["template"]
        prepops = build_item["prepop"]
        db_types = build_item["db_type"]
        max_depth = build_item["max_depth"]
        build_id = build_item["id"]

        # build triggered now
        if "date" in build_item:
            build_date = build_item["date"]
        # build triggered at night
        else:
            build_date = time.strftime("%d.%m.%Y")

        log_name = "log.txt"

        abs_results_folder = os.path.join(request.folder, "static", build_date)
        results_folder = os.path.join("static", build_date)

        if not os.path.exists(abs_results_folder):
            os.makedirs(abs_results_folder)

        log_file_path = os.path.join(abs_results_folder, log_name)
        log_file = open(log_file_path, "w")



        db(table.id == build_id).update(log_file=os.path.join(results_folder,
                                                              log_name
                                                             )
                                        )
        db.commit()

        configure_items = db(s3db.nightly_configure.id > 0).select()
        configure_item = configure_items.first().as_dict()

        web2py_folder = os.path.join(request.folder, "..", "..")

        app_name = configure_item["app_name"]
        edentest_config = os.path.join(request.folder,
                                       "uploads",
                                       configure_item["edentest_config"]
                                      )

        location = os.path.join(web2py_folder, "applications", app_name)

        # # clone the branch
        # run_process("cloning",
        #             "git",
        #             "clone",
        #             repo_url,
        #             "-b",
        #             branch,
        #             location
        #             )
        template_list = templates.replace(' ', '').split(',')
        prepop_list = prepops.split(';')
        prepop_list = [str(tuple(prepop.replace(' ', '').split(','))) for prepop in prepop_list]

        db_types_list = db_types.split(';')
        db_types_list = [db_type.replace(' ', '').split(',') for db_type in db_types_list]

        ret_code = 0
        error = False

        for i in range(len(prepop_list)):
            prepop = prepop_list[i]
            template = template_list[i]
            db_types = db_types_list[i]
            for db_type in db_types:
                rc = create_sub_build(template,
                                      db_type,
                                      prepop
                                     )
                if rc in (252, 253, 255):
                    error = True
                    break
                ret_code = ret_code + rc
                # pass

        if not error:
            if not ret_code:
                status = "PASS"
            else:
                status = "FAIL"
        else:
            status = "ERROR"


        name = "Deleting the build"
        log_file.write(make_header(name))
        log_file.close()

        db(table.id == build_id).update(build_status=status)
        db.commit()




        # # delete the directory
        # try:
        #     shutil.rmtree(location)
        # except OSError as e:
        #     # ignore if directory not present
        #     if e.errno == errno.ENOENT:
        #         pass


    tasks["nightly_build"] = nightly_build



# -----------------------------------------------------------------------------
def org_facility_geojson(user_id=None):
    """
        Export GeoJSON[P] Of Facility data

        @param user_id: calling request's auth.user.id or None
    """
    if user_id:
        # Authenticate
        auth.s3_impersonate(user_id)
    # Run the Task & return the result
    s3db.org_facility_geojson()

tasks["org_facility_geojson"] = org_facility_geojson

# -----------------------------------------------------------------------------
if settings.has_module("msg"):

    # -------------------------------------------------------------------------
    def msg_process_outbox(contact_method, user_id=None):
        """
            Process Outbox
            - will normally be done Asynchronously if there is a worker alive

            @param contact_method: one from s3msg.MSG_CONTACT_OPTS
            @param user_id: calling request's auth.user.id or None
        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)
        # Run the Task & return the result
        result = msg.process_outbox(contact_method)
        db.commit()
        return result

    tasks["msg_process_outbox"] = msg_process_outbox

    # -------------------------------------------------------------------------
    def msg_twitter_search(search_id, user_id=None):
        """
            Perform a Search of Twitter
            - will normally be done Asynchronously if there is a worker alive

            @param search_id: one of s3db.msg_twitter_search.id
            @param user_id: calling request's auth.user.id or None

        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)
        # Run the Task & return the result
        result = msg.twitter_search(search_id)
        db.commit()
        return result

    tasks["msg_twitter_search"] = msg_twitter_search

    # -------------------------------------------------------------------------
    def msg_process_keygraph(search_id, user_id=None):
        """
            Process Twitter Search Results with KeyGraph
            - will normally be done Asynchronously if there is a worker alive

            @param search_id: one of s3db.msg_twitter_search.id
            @param user_id: calling request's auth.user.id or None
        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)
        # Run the Task & return the result
        result = msg.process_keygraph(search_id)
        db.commit()
        return result

    tasks["msg_process_keygraph"] = msg_process_keygraph

    # -------------------------------------------------------------------------
    def msg_poll(tablename, channel_id, user_id=None):
        """
            Poll an inbound channel
        """
        if user_id:
            auth.s3_impersonate(user_id)
        # Run the Task & return the result
        result = msg.poll(tablename, channel_id)
        db.commit()
        return result

    tasks["msg_poll"] = msg_poll

    # -----------------------------------------------------------------------------
    def msg_parse(channel_id, function_name, user_id=None):
        """
            Parse Messages coming in from a Source Channel
        """
        if user_id:
            auth.s3_impersonate(user_id)
        # Run the Task & return the result
        result = msg.parse(channel_id, function_name)
        db.commit()
        return result

    tasks["msg_parse"] = msg_parse

    # -------------------------------------------------------------------------
    def notify_check_subscriptions(user_id=None):
        """
            Scheduled task to check subscriptions for updates,
            creates notify_notify tasks where updates exist.
        """
        if user_id:
            auth.s3_impersonate(user_id)
        notify = s3base.S3Notifications()
        return notify.check_subscriptions()

    tasks["notify_check_subscriptions"] = notify_check_subscriptions

    # -------------------------------------------------------------------------
    def notify_notify(resource_id, user_id=None):
        """
            Asynchronous task to notify a subscriber about resource
            updates. This task is created by notify_check_subscriptions.

            @param subscription: JSON with the subscription data
            @param now: lookup date (@todo: remove this)
        """
        if user_id:
            auth.s3_impersonate(user_id)
        notify = s3base.S3Notifications
        return notify.notify(resource_id)

    tasks["notify_notify"] = notify_notify

# -----------------------------------------------------------------------------
if settings.has_module("req"):

    def req_add_from_template(req_id, user_id=None):
        """
            Add a Request from template
        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)
        # Run the Task & return the result
        result = s3db.req_add_from_template(req_id)
        db.commit()
        return result

    tasks["req_add_from_template"] = req_add_from_template

# -----------------------------------------------------------------------------
if settings.has_module("setup"):

    def deploy(playbook, private_key, host=["127.0.0.1"], only_tags="all", user_id=None):

        pb = s3db.setup_create_playbook(playbook, host, private_key, only_tags)
        pb.run()

        processed_hosts = sorted(pb.stats.processed.keys())

        for h in processed_hosts:
            t = pb.stats.summarize(h)
            if t["failures"] > 0:
                raise Exception("One of the tasks failed")
            elif t["unreachable"] > 0:
                raise Exception("Host unreachable")

    tasks["deploy"] = deploy

    def setup_management(_type, instance_id, deployment_id, user_id=None):
        import ansible.runner
        s3db = current.s3db
        db = current.db

        # get all servers associated
        stable = s3db.setup_server
        servers = db(stable.deployment_id == deployment_id).select(stable.role,
                                                                   stable.host_ip,
                                                                   orderby=stable.role
                                                                   )

        # get deployment

        dtable = s3db.setup_deployment
        deployment = db(dtable.id == deployment_id).select(dtable.private_key,
                                                           dtable.remote_user,
                                                           limitby=(0, 1)).first()
        private_key = os.path.join(current.request.folder, "uploads", deployment.private_key)

        hosts = [server.host_ip for server in servers]
        inventory = ansible.inventory.Inventory(hosts)

        tasks = []
        runner = ansible.runner.Runner

        itable = s3db.setup_instance
        instance = db(itable.id == instance_id).select(itable.type,
                                                       limitby=(0, 1)).first()
        instance_types = ["prod", "test", "demo"]

        if _type == "clean":

            host_ip = servers[0].host_ip

            arguments = [dict(module_name = "service",
                              module_args={"name": "uwsgi",
                                           "status": "stop",
                                           },
                              remote_user=deployment.remote_user,
                              private_key_file=private_key,
                              pattern=host_ip,
                              inventory=inventory,
                              sudo=True
                              ),
                          dict(module_name = "command",
                              module_args="clean %s" % instance_types[instance.type - 1],
                              remote_user=deployment.remote_user,
                              private_key_file=private_key,
                              pattern=host_ip,
                              inventory=inventory,
                              sudo=True
                              ),
                          dict(module_name = "command",
                              module_args="clean_eden %s" % instance_types[instance.type - 1],
                              remote_user=deployment.remote_user,
                              private_key_file=private_key,
                              pattern=servers[0].host_ip,
                              inventory=inventory,
                              sudo=True
                              ),
                          dict(module_name = "service",
                              module_args={"name": "uwsgi",
                                           "status": "start",
                                           },
                              remote_user=deployment.remote_user,
                              private_key_file=private_key,
                              pattern=host_ip,
                              inventory=inventory,
                              sudo=True
                              ),
                          ]

            if len(servers) > 1:
                host_ip = servers[2].host_ip
                arguments[0]["pattern"] = host_ip
                arguments[2]["pattern"] = host_ip
                arguments[3]["pattern"] = host_ip

            for argument in arguments:
                tasks.append(runner(**argument))

            # run the tasks
            for task in tasks:
                response = task.run()
                if response["dark"]:
                    raise Exception("Error contacting the server")

        elif _type == "eden":
            argument = dict(module_name="command",
                            module_args="pull %s" % [instance_types[instance.type - 1]],
                            remote_user=deployment.remote_user,
                            private_key_file=private_key,
                            pattern=servers[0].host_ip,
                            inventory=inventory,
                            sudo=True
                            )

            if len(servers) > 1:
                argument["pattern"] = servers[2].host_ip

            task = runner(**argument)
            response = task.run()
            if response["dark"]:
                raise Exception("Error contacting the server")

    tasks["setup_management"] = setup_management

# --------------------e--------------------------------------------------------
if settings.has_module("stats"):

    def stats_demographic_update_aggregates(records=None, user_id=None):
        """
            Update the stats_demographic_aggregate table for the given
            stats_demographic_data record(s)

            @param records: JSON of Rows of stats_demographic_data records to
                            update aggregates for
            @param user_id: calling request's auth.user.id or None
        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)
        # Run the Task & return the result
        result = s3db.stats_demographic_update_aggregates(records)
        db.commit()
        return result

    tasks["stats_demographic_update_aggregates"] = stats_demographic_update_aggregates

    # -------------------------------------------------------------------------
    def stats_demographic_update_location_aggregate(location_level,
                                                    root_location_id,
                                                    parameter_id,
                                                    start_date,
                                                    end_date,
                                                    user_id=None):
        """
            Update the stats_demographic_aggregate table for the given location and parameter
            - called from within stats_demographic_update_aggregates

            @param location_level: gis level at which the data needs to be accumulated
            @param root_location_id: id of the location
            @param parameter_id: parameter for which the stats are being updated
            @param start_date: start date of the period in question
            @param end_date: end date of the period in question
            @param user_id: calling request's auth.user.id or None
        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)
        # Run the Task & return the result
        result = s3db.stats_demographic_update_location_aggregate(location_level,
                                                                  root_location_id,
                                                                  parameter_id,
                                                                  start_date,
                                                                  end_date,
                                                                  )
        db.commit()
        return result

    tasks["stats_demographic_update_location_aggregate"] = stats_demographic_update_location_aggregate

    # -------------------------------------------------------------------------
    if settings.has_module("vulnerability"):

        def vulnerability_update_aggregates(records=None, user_id=None):
            """
                Update the vulnerability_aggregate table for the given
                vulnerability_data record(s)

                @param records: JSON of Rows of vulnerability_data records to update aggregates for
                @param user_id: calling request's auth.user.id or None
            """
            if user_id:
                # Authenticate
                auth.s3_impersonate(user_id)
            # Run the Task & return the result
            result = s3db.vulnerability_update_aggregates(records)
            db.commit()
            return result

        tasks["vulnerability_update_aggregates"] = vulnerability_update_aggregates

        # ---------------------------------------------------------------------
        def vulnerability_update_location_aggregate(#location_level,
                                                    root_location_id,
                                                    parameter_id,
                                                    start_date,
                                                    end_date,
                                                    user_id=None):
            """
                Update the vulnerability_aggregate table for the given location and parameter
                - called from within vulnerability_update_aggregates

                @param location_level: gis level at which the data needs to be accumulated
                @param root_location_id: id of the location
                @param parameter_id: parameter for which the stats are being updated
                @param start_date: start date of the period in question
                @param end_date: end date of the period in question
                @param user_id: calling request's auth.user.id or None
            """
            if user_id:
                # Authenticate
                auth.s3_impersonate(user_id)
            # Run the Task & return the result
            result = s3db.vulnerability_update_location_aggregate(#location_level,
                                                                  root_location_id,
                                                                  parameter_id,
                                                                  start_date,
                                                                  end_date,
                                                                  )
            db.commit()
            return result

        tasks["vulnerability_update_location_aggregate"] = vulnerability_update_location_aggregate

# --------------------e--------------------------------------------------------
if settings.has_module("disease"):

    def disease_stats_update_aggregates(records=None, all=False, user_id=None):
        """
            Update the disease_stats_aggregate table for the given
            disease_stats_data record(s)

            @param records: JSON of Rows of disease_stats_data records to
                            update aggregates for
            @param user_id: calling request's auth.user.id or None
        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)
        # Run the Task & return the result
        result = s3db.disease_stats_update_aggregates(records, all)
        db.commit()
        return result

    tasks["disease_stats_update_aggregates"] = disease_stats_update_aggregates

    # -------------------------------------------------------------------------
    def disease_stats_update_location_aggregates(location_id,
                                                 children,
                                                 parameter_id,
                                                 dates,
                                                 user_id=None):
        """
            Update the disease_stats_aggregate table for the given location and parameter
            - called from within disease_stats_update_aggregates

            @param location_id: location to aggregate at
            @param children: locations to aggregate from
            @param parameter_id: parameter to aggregate
            @param dates: dates to aggregate for
            @param user_id: calling request's auth.user.id or None
        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)
        # Run the Task & return the result
        result = s3db.disease_stats_update_location_aggregates(location_id,
                                                               children,
                                                               parameter_id,
                                                               dates,
                                                               )
        db.commit()
        return result

    tasks["disease_stats_update_location_aggregates"] = disease_stats_update_location_aggregates

# -----------------------------------------------------------------------------
if settings.has_module("sync"):

    def sync_synchronize(repository_id, user_id=None, manual=False):
        """
            Run all tasks for a repository, to be called from scheduler
        """

        auth.s3_impersonate(user_id)

        rtable = s3db.sync_repository
        query = (rtable.deleted != True) & \
                (rtable.id == repository_id)
        repository = db(query).select(limitby=(0, 1)).first()
        if repository:
            sync = s3base.S3Sync()
            status = sync.get_status()
            if status.running:
                message = "Synchronization already active - skipping run"
                sync.log.write(repository_id=repository.id,
                               resource_name=None,
                               transmission=None,
                               mode=None,
                               action="check",
                               remote=False,
                               result=sync.log.ERROR,
                               message=message)
                db.commit()
                return sync.log.ERROR
            sync.set_status(running=True, manual=manual)
            try:
                sync.synchronize(repository)
            finally:
                sync.set_status(running=False, manual=False)
        db.commit()
        return s3base.S3SyncLog.SUCCESS

    tasks["sync_synchronize"] = sync_synchronize

# -----------------------------------------------------------------------------
# Instantiate Scheduler instance with the list of tasks
s3.tasks = tasks
s3task = s3base.S3Task()
current.s3task = s3task

# -----------------------------------------------------------------------------
# Reusable field for scheduler task links
scheduler_task_id = S3ReusableField("scheduler_task_id",
                                    "reference %s" % s3base.S3Task.TASK_TABLENAME,
                                    ondelete="CASCADE")
s3.scheduler_task_id = scheduler_task_id

# END =========================================================================
