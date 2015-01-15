# coding=utf-8

"""
Utility functions for Maven release automation scripts.
"""

__author__ = "Zmicier Zaleznicenka"
__copyright__ = "Copyright 2015 Zmicier Zaleznicenka"
__license__ = "Apache License, Version 2.0"

__version__ = "0.0.1"
__status__ = "Prototype"
__maintainer__ = "Zmicier Zaleznicenka"
__email__ = "Zmicier.Zaleznicenka@gmail.com"

import argparse
import logging
import os
from subprocess import check_call, CalledProcessError, check_output
import time

LOG_FILE = 'release.log'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

MAIN_BRANCH_NAME = 'master'
RELEASE_BRANCH_NAME = 'release/%s'
RELEASE_BRANCH_VERSION = '%s.1-SNAPSHOT'

# Maven instruction arguments
MVN_USE_RELEASES = ['versions:use-releases', 'scm:checkin', '-DgenerateBackupPoms=false',
                    '-Dmessage=[maven-versions-plugin] set release versions for %s dependencies']
MVN_USE_RELEASES_TEST = ['versions:use-releases', 'scm:checkin', '-DgenerateBackupPoms=false',
                         '-Dmessage=[maven-versions-plugin] set release versions for %s dependencies',
                         '-DpushChanges=false']

# If dev and/or release versions are specified as command-line arguments, they will be added as Maven parameters as well
MVN_RELEASE = ['release:clean', 'release:prepare', 'release:perform']
MVN_RELEASE_TEST = ['release:clean', 'release:prepare', '-DpushChanges=false']

MVN_USE_NEXT_SNAPSHOTS = ['versions:use-next-snapshots', 'scm:checkin', '-DgenerateBackupPoms=false',
                          '-Dmessage=[maven-versions-plugin] set next-snapshots versions for %s dependencies']
MVN_USE_NEXT_SNAPSHOTS_TEST = ['versions:use-next-snapshots', 'scm:checkin', '-DgenerateBackupPoms=false',
                               '-Dmessage=[maven-versions-plugin] set next-snapshots versions for %s dependencies',
                               '-DpushChanges=false']

MVN_RELEASE_BRANCH = ['release:branch', '-DbranchName=%s', '-DreleaseVersion=%s',
                      '-DupdateBranchVersions=true', '-DupdateWorkingCopyVersions=false',
                      '-DautoVersionSubmodules=true']

MVN_RELEASE_BRANCH_TEST = ['release:branch', '-DbranchName=%s', '-DreleaseVersion=%s',
                           '-DupdateBranchVersions=true', '-DupdateWorkingCopyVersions=false',
                           '-DautoVersionSubmodules=true', '-DpushChanges=false']

MVN_UPDATE_VERSIONS = ['release:update-versions', 'scm:checkin',
                       '-Dmessage=[maven-release-plugin] update versions of %s in release branch',
                       '-DautoVersionSubmodules=true', '-DdevelopmentVersion=%s']

MVN_UPDATE_VERSIONS_TEST = ['release:update-versions', 'scm:checkin',
                            '-Dmessage=[maven-release-plugin] update versions of %s in release branch',
                            '-DautoVersionSubmodules=true', '-DdevelopmentVersion=%s', '-DpushChanges=false']

MVN_DEPLOY = ['clean', 'deploy', '-DskipTests']
MVN_DEPLOY_TEST = ['clean', 'deploy', '-DskipTests']

GIT_FIND_CLOSEST_TAG = ['git', 'describe', '--abbrev=0']

GIT_CHECKOUT_BRANCH = ['git', 'checkout', '%s']


def configure_logging():
    """
    Configure logging working with both file (DEBUG level) and console (INFO level)
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)


def prepare_for_release():
    """
    Execute release preparation checks and routines
    """
    if os.path.isfile(LOG_FILE):
        os.remove(LOG_FILE)
    configure_logging()


LOG = logging.getLogger(__name__)
prepare_for_release()


def parse_options():
    """
    Parse command-line options submitted to the script
    See https://docs.python.org/2/library/argparse.html for usage
    """
    parser = argparse.ArgumentParser(description='Maven release automation script')
    parser.add_argument('-b', '--release-branch-only', default=False, required=False, action='store_true',
                        help='don\'t do a new release, only create a release branch')
    parser.add_argument('-d', '--dev_version', dest='dev_version',
                        help='new snapshot version to be set after the release is performed')
    parser.add_argument('-nb', '--no-release-branch', default=False, required=False, action='store_true',
                        help='don\'t create a release branch')
    parser.add_argument('-o', '--only', required=False,
                        help='if you want to release a single component only, set its name in this option')
    parser.add_argument('-r', '--release_version', dest='release_version', help='version to be released')
    parser.add_argument('-s', '--start-from', required=False, dest='start_from',
                        help='If you want to continue aborted release from some component, set its name in this option')
    # TODO set default to False after the code is production-ready
    parser.add_argument('-t', '--test-mode', default=True, required=False, action='store_true',
                        help='test mode disables Stash update and deployment to Nexus')
    options = parser.parse_args()

    if options.dev_version and not options.dev_version.endswith('-SNAPSHOT'):
        LOG.error('Development version should end with -SNAPSHOT')
        raise ValueError

    if not options.test_mode:
        LOG.warn('Production release will be started in 5 seconds; released artifacts will be deployed to Nexus')
        time.sleep(5)

    return options


def define_components_to_release(all_components, options):
    """
    Make changes to the provided list of components given command-line options using the following algorithm
    - if options.only is set, use its value as a name of a single component to be released
    - if options.start_from is set, remove all the components that precede the value of options.start_from
    - otherwise don't make any changes
    :param all_components: [str]: full list of components to be released in correct order
    :param options: [str]: command-line script options
    """
    if not options.only and not options.start_from:
        components = all_components[:]
    elif options.only:
        components = [options.only]
    else:
        index = all_components.index(options.start_from)
        components = all_components[index:]
    LOG.info('components to be released: %s' % ', '.join(components))
    return components


def exec_maven_command(pom_path, component, args):
    """
    Execute a Maven command with -B and -U switches for given pom.xml file.
    :param pom_path: str: relative path to maven pom.xml file to be used
    :param component: str: name of the component being released at the moment
    :param args: [str]: sequence of other command-line arguments to mvn command
    """
    try:
        exec_os_command(['mvn', '-B', '-U', '-f', pom_path] + args)
    except CalledProcessError:
        LOG.error("An error occurred while releasing %s, release stops" % component)
        raise


def exec_os_command_with_output(args):
    """
    Execute OS terminal command given its arguments. Return its output as a byte string.
    On error exit status raise an exception.
    :param args: [str]: command with its arguments
    :return output: str: command output
    """
    with open(LOG_FILE, 'a') as log_file:
        return check_output(args, stderr=log_file)


def exec_os_command(args):
    """
    Execute OS terminal command given its arguments. Write all output to a log file.
    On error exit status raise an exception.
    :param args: [str]: command with its arguments
    """
    with open(LOG_FILE, 'a') as log_file:
        check_call(args, stdout=log_file, stderr=log_file)


def resolve_arguments_placeholder(arguments, predicate, value):
    """
    In a list of maven command-line arguments find element using a predicate and replace a placeholder in it
    with a given value.
    :param arguments: [str]: list of Maven command-line arguments
    :param predicate: predicate function
    :param value: str: replacement value
    """
    # noinspection PyDocstring
    def generator():
        for argument in arguments:
            if predicate(argument):
                yield argument % value
            else:
                yield argument

    return list(generator())


def use_releases(pom_path, component, options):
    """
    # TODO document
    :param options: [str]: command-line script options
    :param pom_path: str: relative path to maven pom.xml file to be used
    :param component: str: name of the component being released at the moment
    """
    LOG.info("updating snapshot versions of %s dependencies to release..." % component)
    args = MVN_USE_RELEASES_TEST[:] if options.test_mode else MVN_USE_RELEASES[:]
    args = resolve_arguments_placeholder(args, lambda x: x.find('Dmessage') > -1, component)
    exec_maven_command(pom_path, component, args)
    LOG.info("snapshot versions updated to release")


def perform_release(pom_path, component, options):
    """
    Run Maven release plugin to prepare and perform the release
    :param pom_path: str: relative path to maven pom.xml file to be used
    :param component: str: name of the component being released at the moment
    :param options: [str]: command-line script options
    """
    args = MVN_RELEASE_TEST[:] if options.test_mode else MVN_RELEASE[:]
    if options.dev_version:
        args.append('-DdevelopmentVersion=' + options.dev_version)
    if options.release_version:
        args.append('-DreleaseVersion=' + options.release_version)

    LOG.info("releasing %s" % component)
    exec_maven_command(pom_path, component, args)
    LOG.info("%s release performed successfully" % component)


def use_next_snapshots(pom_path, component, options):
    """
    # TODO document
    :param pom_path: str: relative path to maven pom.xml file to be used
    :param component: str: name of the component being released at the moment
    :param options: [str]" command-line script options
    """
    LOG.info("updating release versions in %s dependencies to next-snapshots..." % component)
    args = MVN_USE_NEXT_SNAPSHOTS_TEST[:] if options.test_mode else MVN_USE_NEXT_SNAPSHOTS[:]
    args = resolve_arguments_placeholder(args, lambda x: x.find('Dmessage') > -1, component)
    exec_maven_command(pom_path, component, args)
    LOG.info("release versions updated to next-snapshots")


def release_component(path, component, options):
    """
    Releases PPP component
    :param path: str: relative path to the project root
    :param component: str: name of the component being released at the moment
    :param options: [str]: command-line script options
    """
    pom_path = os.path.join(path, component, 'pom.xml')
    LOG.info('starting to release %s' % component)
    use_releases(pom_path, component, options)
    perform_release(pom_path, component, options)
    use_next_snapshots(pom_path, component, options)
    LOG.info(('release of %s completed ' + os.linesep + os.linesep) % component)
    deploy_component(path, component, options)


def update_it_dependencies(path, component, options):
    """
    This function will only update dependencies' versions without performing an actual release.
    It can be useful for integration test projects that do not have to be published.
    :param path: str: relative path to the project root
    :param component: str: name of the component being updated at the moment
    :param options: [str]: command-line script options
    """
    pom_path = os.path.join(path, component, 'pom.xml')
    LOG.info('starting to update %s' % component)
    use_releases(pom_path, component, options)
    use_next_snapshots(pom_path, component, options)
    LOG.info(('update of %s completed ' + os.linesep + os.linesep) % component)


def deploy_component(path, component, options):
    """
    TODO document
    :param path:
    :param component:
    :param options:
    """
    if not options.test_mode:
        pom_path = os.path.join(path, component, 'pom.xml')
        LOG.info('deploying %s' % component)
        args = MVN_DEPLOY_TEST[:] if options.test_mode else MVN_DEPLOY
        exec_maven_command(pom_path, component, args)
        LOG.info('%s deployed' % component)


def create_release_branch(path, component, options):
    """
    Create a branch out of release version from a given component and update its version
    :param path: str: relative path to the project root
    :param component: str: name of the component used as a base for mvn release:branch command
    :param options: [str]: command-line script options
    """
    release = find_release_version(options)
    branch_name = RELEASE_BRANCH_NAME % release
    branch_version = RELEASE_BRANCH_VERSION % release
    pom_path = os.path.join(path, component, 'pom.xml')

    LOG.info('creating release branch %s' % branch_name)
    args = MVN_RELEASE_BRANCH_TEST[:] if options.test_mode else MVN_RELEASE_BRANCH
    args = resolve_arguments_placeholder(args, lambda x: x.find('-DbranchName') > -1, branch_name)
    args = resolve_arguments_placeholder(args, lambda x: x.find('-DreleaseVersion') > -1, branch_version)
    exec_maven_command(pom_path, component, args)
    LOG.info('release branch %s created' % branch_name)
    args = GIT_CHECKOUT_BRANCH[:]
    args = resolve_arguments_placeholder(args, lambda x: x.find('%s') > -1, branch_name)
    exec_os_command(args)
    LOG.info('checked out release branch')
    deploy_component(path, component, options)


def update_project_version(path, component, options):
    """
    TODO document
    :param path:
    :param component:
    :param options:
    """
    release = find_release_version(options)
    branch_version = RELEASE_BRANCH_VERSION % release
    pom_path = os.path.join(path, component, 'pom.xml')

    LOG.info('Updating version of component %s to %s' % (component, branch_version))
    args = MVN_UPDATE_VERSIONS_TEST[:] if options.test_mode else MVN_UPDATE_VERSIONS
    args = resolve_arguments_placeholder(args, lambda x: x.find('-Dmessage') > -1, component)
    args = resolve_arguments_placeholder(args, lambda x: x.find('-DdevelopmentVersion') > -1, branch_version)
    exec_maven_command(pom_path, component, args)
    LOG.info('%s project version updated' % component)
    deploy_component(path, component, options)


def find_release_version(options):
    """
    Derives released version from the closest git tag
    :param options: [str]: command-line script options
    """
    if options.release_version:
        return options.release_version
    else:
        tag = exec_os_command_with_output(GIT_FIND_CLOSEST_TAG)
        return tag[tag.rfind('-') + 1:].rstrip()
