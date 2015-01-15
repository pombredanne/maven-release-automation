#!/usr/bin/env python
# coding=utf-8

"""
Maven release automation script
"""

__author__ = "Zmicier Zaleznicenka"
__copyright__ = "Copyright 2015 Zmicier Zaleznicenka"
__license__ = "Apache License, Version 2.0"

__version__ = "0.0.1"
__status__ = "Prototype"
__maintainer__ = "Zmicier Zaleznicenka"
__email__ = "Zmicier.Zaleznicenka@gmail.com"

import release_common

# Maintain the correct ordering of projects to be released.
# If project B has project A as its dependency, B should be put after A in the list.
ALL_COMPONENTS = ['project-a', 'project-B', 'project-C']

options = release_common.parse_options()

components = release_common.define_components_to_release(ALL_COMPONENTS, options)

if not options.release_branch_only:
    for component in components:
        release_common.release_component('..', component, options)

if not options.no_release_branch:
    release_common.create_release_branch('..', components[0], options)
    for component in components[1:]:
        release_common.update_project_version('..', component, options)

