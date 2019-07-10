#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import github
import github.ContentFile
import re
import typing
from .conventions_apply import argparse_add_which_branch_option, calculate_repo_branch, \
    calculate_branch, GithubRepoBranch
from .util import Configuration


def main():
    parser = argparse.ArgumentParser(description='Fetch dependencies of repo')
    parser.add_argument('--owner_login', type=str, required=True, help='owner of the repo to clone')
    parser.add_argument('--interactive', action='store_true', help='interactive')
    argparse_add_which_branch_option(parser)
    parser.add_argument('repo_name', type=str, help='name of the repo+branch. Format: REPO[:BRANCH]')

    args = parser.parse_args()

    c = Configuration()
    g = c.get_github()

    user_from = g.get_user(args.owner_login)

    repo_branch = calculate_repo_branch(user=user_from, repo_branch_name=args.repo_name)
    if repo_branch.branch is None:
        repo_branch.branch = calculate_branch(repo=repo_branch.repo, branch_dest=args.branch_dest)

    deps, version = repo_branch_dependencies(repo_branch)
    print('version:', version)
    for dep in deps:
        print(dep.reference)

# {, } and % have been added to the regex to catch string operations
CONAN_NAME_REGEX_CHAR_STR = '[a-zA-Z0-9_.+{}%\-]'
CONAN_VERSION_REGEX_CHAR_STR = CONAN_NAME_REGEX_CHAR_STR
CONAN_USER_REGEX_CHAR_STR = CONAN_NAME_REGEX_CHAR_STR
CONAN_CHANNEL_REGEX_CHAR_STR = CONAN_NAME_REGEX_CHAR_STR
CONAN_REF_REGEX_STR = "(?P<ref>(?P<name>{name}+)/(?P<version>{version}+)@(?P<user>{user}+)/(?P<channel>{channel}+))".format(
    name=CONAN_NAME_REGEX_CHAR_STR,
    version=CONAN_VERSION_REGEX_CHAR_STR,
    user=CONAN_USER_REGEX_CHAR_STR,
    channel=CONAN_CHANNEL_REGEX_CHAR_STR
)
CONAN_REF_REGEX = re.compile(CONAN_REF_REGEX_STR)

CONAN_REF_REGEX_IN_CONANFILE_STR = '[\'"]{ref}[\'"]'.format(ref=CONAN_REF_REGEX_STR)
CONAN_REF_REGEX_IN_CONANFILE = re.compile(CONAN_REF_REGEX_IN_CONANFILE_STR)

CONAN_VERSION_REGEX_IN_SOURCE_STR = 'version\s+=\s+[\'"](?P<version>{}+)[\'"]'.format(CONAN_VERSION_REGEX_CHAR_STR)
CONAN_VERSION_REGEX_IN_SOURCE = re.compile(CONAN_VERSION_REGEX_IN_SOURCE_STR)


class ConanReference:
    def __init__(self, name: str, version: str, user: str, channel: str):
        self.name = name
        self.version = version
        self.user = user
        self.channel = channel

    @property
    def reference(self):
        return '{}/{}@{}/{}'.format(self.name, self.version, self.user, self.channel)

    @classmethod
    def from_regex_match(cls, match: typing.Match) -> 'ConanReference':
        if match is None:
            raise ValueError
        return cls(name=match['name'], version=match['version'], user=match['user'], channel=match['channel'])

    @classmethod
    def from_conanfile(cls, text: str) -> typing.List['ConanReference']:
        return list(cls.from_regex_match(m) for m in CONAN_REF_REGEX_IN_CONANFILE.finditer(text))

    @classmethod
    def from_refstr(cls, refstr: str) -> 'ConanReference':
        return cls.from_regex_match(CONAN_REF_REGEX.search(refstr))

    def __repr__(self):
        return '<{}:{}>'.format(type(self).__name__, self.reference)


def repo_branch_dependencies(repo_branch: GithubRepoBranch) -> typing.Tuple[typing.List[ConanReference], typing.Optional[str]]:
    deps = []
    version = None
    for file in ('conanfile.py', 'conanfile_base.py', 'conanfile_installer.py', ):
        try:
            cf: github.ContentFile.ContentFile = repo_branch.repo.get_file_contents(path=file, ref=repo_branch.branch)
        except github.GithubException:
            continue
        text = cf.decoded_content.decode()
        refs = ConanReference.from_conanfile(text)
        deps.extend(refs)

        match = CONAN_VERSION_REGEX_IN_SOURCE.search(text)
        if match:
            version = match['version']
    return deps, version


if __name__ == '__main__':
    main()
