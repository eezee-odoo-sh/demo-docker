# -*- coding: utf-8 -*-
# ############################################################################
#
#    Copyright Eezee-It (C) 2016
#    Author: Eezee-It <info@eezee-it.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
import logging
import os
import shutil
from os.path import basename, normpath

import colorama
from invoke import task

colorama.init()
LOG_COLORS = {
    logging.ERROR: colorama.Fore.RED,
    logging.WARNING: colorama.Fore.YELLOW,
    logging.INFO: colorama.Fore.GREEN,
    logging.DEBUG: colorama.Fore.MAGENTA,
}


class ColorFormatter(logging.Formatter):

    def __init__(self, format="%(message)s"):
        """Create a new formatter that adds colors"""
        super(ColorFormatter, self).__init__(format)

    def format(self, record, *args, **kwargs):
        if record.levelno in LOG_COLORS:
            record.msg = LOG_COLORS[record.levelno] \
                + record.msg + colorama.Style.RESET_ALL
        return super(ColorFormatter, self).format(record, *args, **kwargs)


# Logging
log = logging.getLogger('tasks')
_output = logging.StreamHandler()
_output.setFormatter(ColorFormatter())
log.addHandler(_output)
log.setLevel(logging.DEBUG)


class TaskInterface:

    def __init__(self, configuration):
        self.c = configuration

    @staticmethod
    def get_task_gateway(c):
        if c.use_local:
            return LocalTaskGateway(c)

        if c.use_docker:
            return DockerTaskGateway(c)

    def init(self, database_name=''):
        log.info("Not implemented")

    def start(self, database_name=''):
        log.info("Not implemented")

    def stop(self, database_name=''):
        log.info("Not implemented")

    def run(self, addons_to_update, addons_to_install, database_name=''):
        log.info("Not implemented")

    def clean(self, database_name='', **params):
        log.info("Not implemented")

    def clean_test(self, database_name='', **params):
        log.info("Not implemented")

    def _get_database_name(self, database_name='', for_test=False):
        if for_test:
            database = database_name or self.c.test_database_name
            log.debug('Database: %s ' % database)
            return database

        database = database_name or self.c.database_name
        log.debug('Database: %s ' % database)
        return database

    def _get_database_name_for_test(self, database_name='', for_test=True):
        return self._get_database_name(database_name)

    def _execute_command(self, command):
        log.debug(command)
        self.c.run(command)


class LocalTaskGateway(TaskInterface):

    def __init__(self, configuration):
        super(LocalTaskGateway, self).__init__(configuration)
        log.info('• Using Local gateway')

    def init(self, database_name='', update=False):
        """Initialize a local database"""
        command = _get_odoo_base_command(self.c, database_name)
        command += ' --stop-after-init '
        addons = ",".join(_get_odoo_addons(self.c))
        command += ('-u' if update else '-i') + ' ' + addons
        self.c.run(command)

    def start(self, database_name=''):
        command = _get_odoo_base_command(self.c, database_name)
        self.c.run(command)

    def clean(self, database_name='', **params):
        log.info('• Cleaning Database')
        self.c.run("dropdb %s --if-exists" %
                   self._get_database_name(database_name))

    def clean_test(self, c, database_name='', **params):
        self.clean(c, database_name, **params)
        log.info('• Cleaning coverage data')
        if os.path.exists('.coverage'):
            os.remove('.coverage')

        if os.path.exists('htmlcov'):
            shutil.rmtree('htmlcov')


class DockerTaskGateway(TaskInterface):

    def __init__(self, configuration):
        super(DockerTaskGateway, self).__init__(configuration)
        log.info('• Using Docker gateway')

    def init(self, database_name='', update=False, **params):
        """Initialize a local database"""

        database = self._get_database_name(database_name)
        self.clean(database_name)

        if not params.get("ignore_image_build"):
            log.info('• Creating Docker image')
            command = "docker build . -t %s" % self.c.doker_image_name
            self._execute_command(command)

        filstore_volume = "%s_filestore" % self.c.odoo_container_name
        log.info('• Create volume to store Odoo filestore')
        command = "docker volume create %s" % filstore_volume
        self._execute_command(command)

        log.info('• Initial Odoo database')
        command = self._get_docker_base_command()
        command += "-- -i %s -d %s --stop-after-init" % (
            self.c.main_project_addons, database)
        self._execute_command(command)

        # Recreate new not stopped docker container (because the last command
        # have --stop-after-init)
        command = "docker container rm %s --force || true" % (
            self.c.odoo_container_name)
        self._execute_command(command)

        command = self._get_docker_base_command(background=True)
        self._execute_command(command)

        self.stop()

        # if c.use_docker_compose:
        #     # Start docker
        #     local_run(c, database_name)
        #     db = _get_database_name(c, database_name, True)
        #     addons = ",".join(_get_odoo_addons(c))
        #     command = 'docker-compose run --rm web -d %s ' % (db)
        #     command += ('-u' if update else '-i') + ' ' + addons
        #     command += ' --stop-after-init'

        #     c.run(command)
        #     return

    def start(self, database_name=''):
        command = "docker start %s" % self.c.odoo_container_name
        self._execute_command(command)

        log.info("run 'docker logs %s --follow' to see Odoo log" % (
            self.c.odoo_container_name))

    def stop(self, database_name=''):
        command = "docker stop %s" % self.c.odoo_container_name
        self._execute_command(command)

    def run(self, addons_to_update, addons_to_install, database_name=''):
        database = self._get_database_name(database_name)

        # First remove the old container
        log.info('• Remove old container')
        command = "docker container rm %s --force || true" % (
            self.c.odoo_container_name)
        self._execute_command(command)

        # create the new container and update Odoo
        log.info('• Update Odoo')
        command = self._get_docker_base_command()

        command += "-- -d %s" % database

        if addons_to_update:
            command += " -u %s " % addons_to_update

        if addons_to_install:
            command += " -i %s " % addons_to_install

        self._execute_command(command)

    def clean(self, database_name='', **params):

        log.info('• Remove docker container')
        command = "docker rm -v %s --force || true" % (
            self.c.odoo_container_name)
        self._execute_command(command)

        log.info('• Remove docker image')
        command = "docker image rm %s || true" % self.c.doker_image_name
        self._execute_command(command)

        log.info('• Remove docker volume')
        filstore_volume = "%s_filestore" % self.c.odoo_container_name
        command = "docker volume rm %s || true" % filstore_volume
        self._execute_command(command)

        log.info('• Cleaning Database')
        database = self._get_database_name(database_name)
        command = "docker exec %s dropdb %s --if-exists -U odoo" % (
            self.c.db_container_name, database)

        self._execute_command(command)

        log.info('For more clean run: docker system prune -a or'
                 ' docker system prune -a --volumes')

    def _get_docker_base_command(self, background=False):
        filstore_volume = "%s_filestore" % self.c.odoo_container_name
        command = "docker run"
        if background:
            command += " -d "
        command += " -v %s:/var/lib/odoo" % (filstore_volume)

        for volume in self.c.data_volumes:
            command += " -v %s/%s " % (os.getcwd(), volume)

        command += " -p %s:8069 " % self.c.odoo_port
        command += "--name %s --link %s:db" % (
            self.c.odoo_container_name, self.c.db_container_name)
        command += " -t %s " % self.c.doker_image_name

        return command

# ##############################################################
# tasks
# ##############################################################


@task()
def init(c, database_name='', update=False, ignore_image_build=False):
    """Run odoo"""
    gateway = TaskInterface.get_task_gateway(c)
    extra_params = {
        'ignore_image_build': ignore_image_build
    }
    gateway.init(database_name, update, **extra_params)


@task()
def start(c, database_name=''):
    """Run odoo"""
    gateway = TaskInterface.get_task_gateway(c)
    gateway.start(database_name)


@task()
def stop(c, database_name=''):
    """Stop odoo"""
    gateway = TaskInterface.get_task_gateway(c)
    gateway.stop(database_name)


@task
def clean(c, database_name=''):
    """Remove the database and generated files"""
    gateway = TaskInterface.get_task_gateway(c)
    gateway.clean(database_name)


@task
def clean_test(c, database_name=''):
    """Remove the database and generated files on test"""
    gateway = TaskInterface.get_task_gateway(c)
    gateway.clean_test(database_name)


@task
def run(c, u='', i='', database_name=''):
    gateway = TaskInterface.get_task_gateway(c)
    gateway.run(u, i, database_name)


@task
def lint_flake8(c, addons=''):
    """Run flake8"""
    log.info('• Flake8')
    paths = ['.']

    if addons:
        paths = _find_addons_path(c, addons.split(','))

    flakerc = '.flake8'
    for path in paths:
        command = "flake8 %s --config=%s" % (path, flakerc)
        c.run(command)


@task
def lint_odoo_lint(c, addons=''):
    """Run pylint"""
    log.info('• pyLinter')

    if addons:
        addons = _find_addons_path(c, addons.split(','))
    else:
        addons = _find_addons_path(c, _get_odoo_addons(c))

    command = "pylint --errors-only --load-plugins=pylint_odoo -d all -e odoolint" + \
        " %s --disable=%s "

    if c.debug:
        log.debug('Addon list')
        log.debug(str(addons))

    for addon in addons:
        addon_name = basename(normpath(addon))
        log.debug("Pylint check addon: %s" % addon_name)
        c.run(command % (addon, c.odoo_lint_disable))


@task
def lint_xml(c, addons=''):
    """Run xmllint"""
    log.info('• XML Linter')
    if os.name == 'nt':
        log.warning('Skip test on Windows')
        return
    c.run('find . -maxdepth 4 -type f -iname "*.xml" '
          '| xargs -I \'{}\' xmllint -noout \'{}\'')


@task()
def lint(c, addons=''):
    """Run static code checks"""
    lint_xml(c, addons)
    lint_flake8(c, addons)
    lint_odoo_lint(c, addons)

# Unit tests task(s)


@task()
def unittest(c, with_coverage=False, addons='', build=False, database_name=''):
    """Launch unit tests"""
    log.info('• Unittest')

    if not addons:
        addons = ",".join(_get_odoo_addons(c))

    if not with_coverage:
        with_coverage = c.with_coverage

    if build:
        clean(c, database_name)
        _prepare_odoo(c, addons, database_name)

    log.info('• Launch test(s)')

    command = _unittest_odoo_command(c, addons, database_name)

    if with_coverage:
        _run_coverage(c, command)

    else:
        c.run(command)


@task()
def test(c, with_coverage=False, addons='', build=False, database_name=''):
    """Static code analysis and tests"""
    lint(c, addons)
    unittest(c, with_coverage, addons, build, database_name)


def _unittest_odoo_command(c, addons, database_name):
    command = _get_odoo_base_command(c, database_name)
    command += " --test-enable --log-level=%s" % c.test_log_level
    command += " --workers=0 --smtp=nosmtp"
    command += "%s" % _get_lang_handler_command_arg(c)
    command += " --stop-after-init -u %s" % addons

    if c.debug:
        log.debug("Unittest Command")
        log.debug(command)
    return command


def _get_lang_handler_command_arg(c):
    command_arg = ''
    log_handlers = c.test_log_handlers.split(",")
    for handler in log_handlers:
        command_arg += " --log-handler=%s " % handler
    return command_arg


# @task()
# def local_init(c, database_name='', update=False):
#     """Initialize a local database"""
#     if c.use_docker_compose:
#         # Start docker
#         local_run(c, database_name)
#         db = _get_database_name(c, database_name, True)
#         addons = ",".join(_get_odoo_addons(c))
#         command = 'docker-compose run --rm web -d %s ' % (db)
#         command += ('-u' if update else '-i') + ' ' + addons
#         command += ' --stop-after-init'

#         c.run(command)
#         return

#     command = _get_odoo_base_command(c, database_name)
#     command += ' --stop-after-init '
#     addons = ",".join(_get_odoo_addons(c))
#     command += ('-u' if update else '-i') + ' ' + addons
#     c.run(command)


@task()
def local_update(c, addons, database_name=''):
    """Run odoo from a local database"""
    if c.use_docker_compose:
        db = _get_database_name(c, database_name, True)
        # Run the update
        command = 'docker-compose run --rm web -d %s -u %s' % (db, addons)
        command += ' --stop-after-init'
        c.run(command)

        # Restart container
        command = 'docker-compose restart web'
        c.run(command)
        return


@task()
def local_stop(c):
    """Run odoo from a local database"""
    if c.use_docker_compose:
        # Start docker
        command = 'docker-compose down'
        c.run(command)
        return


@task()
def show_addons(c, addons=''):
    """Show availabe addons"""
    if not addons:
        addons = _get_odoo_addons(c)

    for addon in addons:
        log.debug(addon)


@task()
def show_addons_directories(c, addons=''):
    """Show addon directories"""
    _get_addons_from_directories(c, c.custom_addons_directories)


def _prepare_odoo(c, addons, database_name):
    log.info('    • Preparing Odoo for test')
    command = _get_odoo_base_command(c, database_name)
    command += " --log-level=error --log-handler=odoo.modules.loading:INFO "
    command += "--workers=0 --smtp=nosmtp"
    command += " --stop-after-init -i %s" % addons
    c.run(command)


def _run_coverage(c, odoo_command):
    command = "coverage run %s && coverage html && coverage report -i " % odoo_command
    c.run(command)


def _get_odoo_base_command(c, database_name=''):
    command = [c.odoo_bin_directory + '/odoo-bin']
    if os.path.isfile(c.odoo_conf):
        command.extend(['-c', c.odoo_conf])
    else:
        log.debug("Use no Odoo configuration parameter")

    addons = _get_addons_path(c)
    command.append('--addons-path=' + addons)
    if c.debug:
        log.debug("Addons path: " + addons)

    if c.odoo_languages:
        command.append('--load-language=%s' % (",".join(c.odoo_languages)))
        if c.debug:
            log.debug("Lang to install:")
            log.debug(",".join(c.odoo_languages))

    db = _get_database_name(c, database_name)
    command.extend(['-d', db, '--db-filter', db])

    odoo_base_command = " ".join(command)
    if c.debug:
        log.debug("Odoo base command")
        log.debug(odoo_base_command)
    return odoo_base_command


def _get_odoo_addons(c):
    addons = []

    if c.custom_addons:
        addons += c.custom_addons

    if c.custom_addons_directories:
        addons += _get_addons_from_directories(c, c.custom_addons_directories)

    return addons


def _get_addons_from_directories(c, directories):

    addons = []
    for directory in directories:
        if c.debug:
            log.debug("Directory to fetch Odoo addons")
            log.debug(directory)
        addons += _get_addons_from_directory(get_project_base(c) + directory)
    return addons


def _get_addons_from_directory(directory):
    addons = []
    for item in os.listdir(directory):
        if not os.path.isfile(directory + "/" + item) and not item[0] == '.':
            addons.append(item)

    return addons


def _get_addons_path(c):
    if not c.custom_addons_directories:
        return []

    addons_path = []

    for addon_directory in c.odoo_addons_directories:
        addons_path.append(get_project_base(c) + addon_directory)

    for addon_directory in c.custom_addons_directories:
        addons_path.append(get_project_base(c) + addon_directory)

    return ",".join(addons_path)


def _find_addons_path(c, addons):

    addons_path = []
    for addon in addons:
        addons_path.append(_find_addon_path(c, addon))
    return addons_path


def _find_addon_path(c, addon):
    directories = _get_addons_path(c).split(',')
    for directory in directories:
        if not os.path.exists(directory):
            log.warning("Directory %s doesn\'t exists!" % directory)
            continue

        if not os.path.isdir(directory):
            log.warning("Directory %s is not a directory!" % directory)
            continue

        for item in os.listdir(directory):
            if item == addon:
                return directory + '/' + addon

    raise Exception("Module %s not found!" % addon)


def get_project_base(c):
    """Get Odoo projet directory where odoo-bin is located"""
    return os.getcwd() + c.odoo_bin_relative_path
