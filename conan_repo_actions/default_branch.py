#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from collections import OrderedDict
from github.Branch import Branch
from github.Repository import Repository
from conan_repo_actions.util import Configuration, input_ask_question_yn, input_ask_question_options
from packaging.version import Version, InvalidVersion
import re
import typing


def main():
    parser = argparse.ArgumentParser(description='Check and fix default branches')
    parser.add_argument('repo_names', nargs=argparse.ZERO_OR_MORE,
                        help='names of repo to check (skip if check all)')
    parser.add_argument('--owner_login', type=str, required=True,
                        help='owner of the repo to clone')
    parser.add_argument('--fix', action='store_true',
                        help='fix the default branch')

    args = parser.parse_args()

    c = Configuration()
    g = c.get_github()

    loggedin_user = g.get_user()
    owner_user = g.get_user(args.owner_login)

    if args.fix and loggedin_user.id != owner_user.id:
        print('Cannot fix default branches when logged-in user is not the owner of the repos to check')

    if args.repo_names:
        repos_to_check = (owner_user.get_repo(repo_name) for repo_name in args.repo_names)
    else:
        repos_to_check = owner_user.get_repos()

    for repo_to_check in repos_to_check:
        default_branch_check(repo_to_check, fix=args.fix)


def default_branch_check(github_repo: Repository, fix=False):
    repo = ConanRepo.from_repo(github_repo)

    messages = []
    if not repo.contains_conan_branches():
        messages.append('no versions found')

    if repo.contains_unknown_branches():
        messages.append('non-conan branches found ({})'.format(list(b.name for b in repo.unknown_branches)))

    change_default_branch = False
    default_branch_suggestions = list(sorted(repo.branches, key=_BranchRepoSuggestionKey)) + list(repo.unknown_branches)

    if not repo.default_branch.good():
        messages.append('default branch has not the channel/branch format'.format())
    else:
        if repo.default_branch.channel != 'testing':
            messages.append('default channel is not testing'.format())
            change_default_branch = True

        if repo.default_branch.version is None:
            messages.append('cannot decode default branch version')
        else:
            for c in ('stable', 'testing', ):
                try:
                    next(b for b in repo.get_branches_by_version(repo.default_branch.version) if b.channel == c)
                except StopIteration:
                    messages.append('default branch has no "{}" channel equivalent'.format(c))

            if repo.default_branch.version.is_prerelease:
                messages.append('version of default branch is a prerelease')

            assert max(repo.versions) == repo.most_recent_version()

            most_recent_stable_version_overall = repo.version_most_recent_filter(lambda b: not b.version.is_prerelease)

            most_recent_version_testing = repo.most_recent_version_by_channel('testing')
            most_recent_version_overall = repo.most_recent_version()

            if repo.default_branch.version != most_recent_stable_version_overall:
                messages.append('default branch is not on most recent (non-prerelease) version')
                change_default_branch = True

            if most_recent_version_testing != most_recent_version_overall:
                messages.append('most recent version has no testing channel branch')

    if change_default_branch:
        messages.append('suggestions={}'.format(list(b.name for b in default_branch_suggestions)))

    if messages:
        print('{} (default="{}"): {}'.format(github_repo.full_name, repo.default_branch.name, '; '.join(messages)))

    if fix:
        if default_branch_suggestions:
            if len(default_branch_suggestions) == 1:
                print('Only one branch available -> do nothing')
            else:
                options = ['- do nothing -', ] + list(b.name for b in default_branch_suggestions)
                answer = input_ask_question_options('Change default branch to?', options, default=0)
                apply_fixes = answer != 0
                new_default_branch_name = options[answer]
                if apply_fixes:
                    new_default_branch_name = options[answer]
                    confirmation_question = 'Change the default branch of "{}" from "{}" to "{}"?'.format(
                        github_repo.full_name, repo.default_branch.name, new_default_branch_name)
                    apply_fixes = input_ask_question_yn(confirmation_question, default=False)
                if apply_fixes:
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
        self._versionmap = OrderedDict(sorted(versionmap.items(), key=lambda v_b: v_b[0], reverse=True))
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
                yield branch

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

    def most_recent_version_by_channel(self, channel: str) -> typing.Optional[Version]:
        branches = list(self.get_branches_by_channel(channel))
        try:
            return branches[0].version
        except IndexError:
            return None

    def most_recent_version(self) -> typing.Optional[Version]:
        try:
            return list(self._versionmap.keys())[0]
        except IndexError:
            return None

    def branches_filter(self, fn: typing.Callable[[ConanRepoBranch], bool]) -> typing.Iterator[ConanRepoBranch]:
        return filter(fn, self.branches)

    def version_most_recent_filter(self, fn: typing.Callable[[ConanRepoBranch], bool]) -> typing.Optional[Version]:
        try:
            return next(self.branches_filter(fn)).version
        except StopIteration:
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


class _BranchRepoSuggestionKey:
    @classmethod
    def _cmp_version_channel(cls, first: ConanRepoBranch, second: ConanRepoBranch) -> int:
        if first.version == second.version:
            return cls._cmp_channel(first, second)
        if first.version > second.version:
            return -1
        else:
            return 1

    @classmethod
    def _cmp_channel(cls, first: ConanRepoBranch, second: ConanRepoBranch) -> int:
        if first.channel == second.channel:
            return 0
        if first.channel == 'testing':
            return -1
        if second.channel == 'testing':
            return 1
        if first.channel == 'stable':
            return -1
        if second.channel == 'stable':
            return 0
        if first.channel > second.channel:
            return -1
        return 1

    def __init__(self, obj):
        self.obj = obj

    def __lt__(self, other):
        return self._cmp_version_channel(self.obj, other.obj) < 0

    def __gt__(self, other):
        return self._cmp_version_channel(self.obj, other.obj) > 0

    def __eq__(self, other):
        return self._cmp_version_channel(self.obj, other.obj) == 0

    def __le__(self, other):
        return self._cmp_version_channel(self.obj, other.obj) <= 0

    def __ge__(self, other):
        return self._cmp_version_channel(self.obj, other.obj) >= 0

    def __ne__(self, other):
        return self._cmp_version_channel(self.obj, other.obj) != 0


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
