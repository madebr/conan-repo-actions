# -*- coding: utf-8 -*-

import re
from collections import namedtuple
import os
from setuptools import setup, find_packages
from codecs import open


here = os.path.abspath(os.path.dirname(__file__))

# Get the long description from the README file
with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()


def get_requires(filename):
    requirements = []
    with open(os.path.join(here, 'conan_repo_actions', filename)) as req_file:
        for line in req_file.read().splitlines():
            if not line.strip().startswith("#"):
                requirements.append(line)
    return requirements


def load_metadata():
    """Load project metadata from __init__.py file"""
    filename = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            "conan_repo_actions", "__init__.py"))
    Data = namedtuple("Data", ("version", "name", "email", "url", "license", ))

    with open(filename, "rt") as version_file:
        conan_init = version_file.read()
        version = re.search('__version__ = \'([0-9a-zA-Z.-]+)\'', conan_init).group(1)
        m_name_mail = re.search('__author__ = \'([\\w ]+) <([\\w@\\.]+)>\'', conan_init)
        name = m_name_mail.group(1)
        mail = m_name_mail.group(2)
        url = re.search('__url__ = \'([\\w\\/\\.\\:\\-]+)\'', conan_init).group(1)
        license = re.search('__license__ = \'([\\w\\.]+)\'', conan_init).group(1)
        return Data(version, name, mail, url, license)


metadata = load_metadata()

setup(
    name='conan-repo-actions',
    version=metadata.version,
    long_description=long_description,
    description='Scripts to handle conan repos',
    url=metadata.url,
    author=metadata.name,
    author_email=metadata.email,

    license=metadata.license,

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],

    # What does your project relate to?
    keywords=['conan', 'C/C++', 'package', 'libraries', 'developer', 'manager',
              'dependency', 'tool', 'c', 'c++', 'cpp'],

    # You can just specify the packages manually here if your project is
    # simple. Or you can use find_packages().
    packages=find_packages(exclude=['tests']),

    # Alternatively, if you want to distribute just a my_module.py, uncomment
    # this:
    #   py_modules=["my_module"],

    # List run-time dependencies here.  These will be installed by pip when
    # your project is installed. For an analysis of "install_requires" vs pip's
    # requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=get_requires('requirements.txt'),

    # List additional groups of dependencies here (e.g. development
    # dependencies). You can install these using the following syntax,
    # for example:
    # $ pip install -e .[dev,test]
    extras_require={
        'test': get_requires('requirements_test.txt')
    },
\
    package_data={
        'conan_repo_actions': ['*.txt'],
    },
    # If there are data files included in your packages that need to be
    # installed, specify them here.  If using Python 2.6 or less, then these
    # have to be included in MANIFEST.in as well.
    # package_data={
    #     '': ['*.md'],
    # },
    include_package_data=True,

    # Although 'package_data' is the preferred approach, in some case you may
    # need to place data files outside of your packages. See:
    # http://docs.python.org/3.4/distutils/setupscript.html#installing-additional-files # noqa
    # In this case, 'data_file' will be installed into '<sys.prefix>/my_data'
    # data_files=[('my_data', ['data/data_file'])],

    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # pip to create the appropriate form of executable for the target platform.
    entry_points={
        'console_scripts': [
            'conan-repo-actions-fork_create=conan_repo_actions.fork_create:main',
            'conan-repo-actions-fork_cleanup=conan_repo_actions.fork_cleanup:main',
            'conan-repo-actions-default_branch=conan_repo_actions.default_branch:main',
            'conan-repo-actions-conventions_apply=conan_repo_actions.conventions_apply:main',
            'conan-repo-actions-conventions_apply_create_pr=conan_repo_actions.conventions_apply_create_pr:main',
        ],
    },
)
