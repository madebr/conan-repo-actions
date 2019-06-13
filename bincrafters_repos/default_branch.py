#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import github
from github.Branch import Branch
from github.Repository import Repository
from bincrafters_repos import GITHUB_BINCRAFTERS_NAME
from bincrafters_repos.util import Configuration, input_ask_question_yn, input_ask_question_options
from packaging.version import Version, InvalidVersion
import re
import typing


def main():
    parser = argparse.ArgumentParser(description='Check and fix default branches')
    parser.add_argument('repo_names', nargs=argparse.ZERO_OR_MORE,
                        help='names of repo to check (skip if check all)')
    parser.add_argument('--owner_login', type=str, default=GITHUB_BINCRAFTERS_NAME,
                        help='owner of the repo to clone')
    parser.add_argument('--fix', action='store_true',
                        help='fix the default branch')

    args = parser.parse_args()

    c = Configuration()
    l, p = c.github_login

    g = github.Github(l, p)
    loggedin_user = g.get_user()
    owner_user = g.get_user(args.owner_login)

    if args.fix and loggedin_user.id != owner_user.id:
        print('Cannot fix default branches when logged-in user is not the owner of the repos to check')

    if args.repo_names:
        repos_to_check = (owner_user.get_repo(repo_name) for repo_name in args.repo_names)
    else:
        repos_to_check = owner_user.get_repos()

    for repo_to_check in repos_to_check:
        handle_default_branch(repo_to_check, fix=args.fix)


def handle_default_branch(github_repo: Repository, fix=False):
    repo = ConanRepo.from_repo(github_repo)

    messages = []
    if not repo.contains_conan_branches():
        messages.append('no versions found')

    if repo.contains_unknown_branches():
        messages.append('non-conan branches found ({})'.format(list(b.name for b in repo.unknown_branches)))

    default_branch_suggestions = None

    if not repo.default_branch.good():
        messages.append('default branch has not the channel/branch format'.format())
    else:
        if repo.default_branch.channel != 'stable':
            messages.append('default channel is not stable'.format())

        if repo.default_branch.version is None:
            messages.append('cannot decode default branch version')
        else:
            if repo.default_branch.channel == 'stable':
                suggested_channel = 'stable'
            else:
                suggested_channel = None

            if repo.default_branch.version.is_prerelease:
                messages.append('version of default branch is a prerelease')

            most_recent_version_suggested = repo.most_recent_version_by_channel(suggested_channel)
            most_recent_version_stable = repo.most_recent_version_by_channel('stable')
            most_recent_version_overall = repo.most_recent_version_by_channel()

            if most_recent_version_stable != most_recent_version_overall:
                messages.append('most recent version has no stable channel')
            if most_recent_version_suggested and most_recent_version_suggested != repo.default_branch.version:
                messages.append('version of default branch out of date')

                suggested_branches = list(repo.get_branches_by_channel(suggested_channel))
                other_branches = list(sorted((set(repo.branches).difference(set(suggested_branches))),
                                             key=lambda b: b.version, reverse=True))
                unknown_branches = list(repo.unknown_branches)

                default_branch_suggestions = suggested_branches + other_branches + unknown_branches
                messages.append('suggestions={}'.format(list(b.name for b in default_branch_suggestions)))

    if messages:
        print('{} (default="{}"): {}'.format(github_repo.full_name, repo.default_branch.name, '; '.join(messages)))

    if fix:
        if default_branch_suggestions:
            options = ['- do nothing -', ] + list(b.name for b in default_branch_suggestions)
            answer = input_ask_question_options('Change default branch to?', options)
            if answer is None or answer == 0:
                print('Do nothing')
            else:
                new_default_branch_name = options[answer]
                confirmation_question = 'Change the default branch of "{}" from "{}" to "{}"?'.format(
                    github_repo.full_name, repo.default_branch.name, new_default_branch_name)
                change_default_branch = input_ask_question_yn(confirmation_question, default=False)
                if change_default_branch:
                    print('Changing default branch to {} ...'.format(new_default_branch_name))
                    github_repo.edit(default_branch=new_default_branch_name)
                    print('... done'.format(new_default_branch_name))
                else:
                    print('Do nothing')


class ConanRepoBranch(object):
    def __init__(self, name: str):
        self._name = name
        _channel_str_version = _channel_version_str_from_branch(self._name)
        # self._channel_version_from_branch(self._name)
        if _channel_str_version is None:
            self._channel, self._version_str = None, None
        else:
            self._channel, self._version_str = _channel_str_version

    @property
    def name(self) -> str:
        return self._name

    def good(self) -> bool:
        return self._channel is not None

    @property
    def channel(self) -> typing.Optional[str]:
        return self._channel

    @property
    def version_str(self) -> typing.Optional[str]:
        return self._version_str

    @property
    def version(self) -> typing.Optional[Version]:
        if self._version_str is None:
            return None
        return _version_from_string(self._version_str)

    def __repr__(self) -> str:
        return '<{}:{}>'.format(type(self).__name__, self._name)

    def __hash__(self) -> int:
        return hash(self._name)

    def __eq__(self, other: 'ConanRepoBranch') -> bool:
        if type(self) != type(other):
            return False
        return self._name == other._name


class ConanRepo(object):
    def __init__(self, versionmap: typing.Mapping[Version, typing.List[ConanRepoBranch]],
                 unknown: typing.Iterable[ConanRepoBranch], default_branch: ConanRepoBranch):
        self._versionmap = dict(sorted(versionmap.items(), key=lambda v_b: v_b[0], reverse=True))
        self._unknown_branches = list(unknown)
        self._default_branch = default_branch

    @property
    def default_branch(self) -> ConanRepoBranch:
        return self._default_branch

    @property
    def versions(self) -> typing.Iterable[Version]:
        return self._versionmap.keys()

    @property
    def branches(self) -> typing.Iterable[ConanRepoBranch]:
        for _, branches in self._versionmap.items():
            for branch in branches:
                if branch.channel == 'stable':
                    yield branch
            for branch in branches:
                if branch.channel != 'stable':
                    yield branch

    @property
    def non_prerelease_versions(self) -> typing.Iterable[Version]:
        for version in self._versionmap.keys():
            if not version.is_prerelease:
                yield version

    @property
    def unknown_branches(self) -> typing.Iterable[ConanRepoBranch]:
        return iter(self._unknown_branches)

    def contains_conan_branches(self) -> bool:
        return len(self._versionmap) > 0

    def contains_unknown_branches(self) -> bool:
        return len(self._unknown_branches) > 0

    def get_branches_by_version(self, version: Version) -> typing.Iterable[ConanRepoBranch]:
        for branch in self._versionmap.get(version, []):
            yield branch

    def get_branches_by_channel(self, channel: typing.Optional[str]) -> typing.Iterable[ConanRepoBranch]:
        for _, branches in self._versionmap.items():
            for branch in branches:
                if channel is None:
                    yield branch
                else:
                    if channel == branch.channel:
                        yield branch

    def most_recent_version_by_channel(self, channel: typing.Optional[str]=None) -> typing.Optional[Version]:
        if channel is not None:
            branches = list(self.get_branches_by_channel(channel))
            try:
                return branches[0].version
            except IndexError:
                return None
        else:
            try:
                return list(self._versionmap.keys())[0]
            except IndexError:
                return None

    @classmethod
    def from_repo(cls, repo: Repository) -> 'ConanRepo':
        return cls.from_branches(repo.get_branches(), repo.default_branch)

    @classmethod
    def from_branches(cls, branches: typing.Iterable[Branch], default: str) -> 'ConanRepo':
        result = dict()
        unknown = list()
        for branch in branches:
            channel_version = _channel_version_from_branch(branch.name)
            if channel_version is None:
                unknown.append(ConanRepoBranch(branch.name))
                continue
            channel, version = channel_version
            if version is None:
                unknown.append(ConanRepoBranch(branch.name))
            else:
                result.setdefault(version, [])
                result[version].append(ConanRepoBranch(branch.name))
        return cls(versionmap=result, unknown=unknown, default_branch=ConanRepoBranch(default))


def _channel_version_str_from_branch(branch: str) -> typing.Optional[typing.Tuple[str, str]]:
    try:
        [b_str, v_str] = branch.split('/', 1)
        return b_str, v_str
    except ValueError:
        return None


def _channel_version_from_branch(branch: str) -> typing.Optional[typing.Tuple[str, typing.Optional[Version]]]:
    b_v = _channel_version_str_from_branch(branch)
    if b_v is None:
        return None
    b, v_str = b_v
    v = _version_from_string(v_str)
    return b, v
    # try:
    #     [b_str, v_str] = branch.split('/', 1)
    # except ValueError:
    #     return None
    # v = _version_from_string(v_str)
    # return b_str, v


def _version_from_string(v_str: str) -> typing.Optional[Version]:
    try:
        return Version(v_str)
    except InvalidVersion:
        m = re.search(r'r(?P<year>[0-9]{2,4})(?P<subyear>[a-zA-Z]?)', v_str)
        if m:
            major = int(m.group('year'))
            subyear = m.group('subyear')
            if subyear:
                minor_zero = ord('a') - 1
                minor = ord(subyear) - minor_zero
            else:
                minor = 0
            return Version('{}.{}'.format(major, minor))
    return None


if __name__ == '__main__':
    main()
