#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import github
from bincrafters_repos import GITHUB_BINCRAFTERS_NAME
from bincrafters_repos.util import Configuration
from packaging.version import Version, InvalidVersion
import typing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner_login', type=str, default=GITHUB_BINCRAFTERS_NAME,
                        help='owner of the repo to clone')
    parser.add_argument('repo_name', type=str, default=None, nargs=argparse.OPTIONAL,
                        help='name of repo to check (skip if check all)')

    args = parser.parse_args()

    c = Configuration()
    l, p = c.github_login

    g = github.Github(l, p)
    from_user = g.get_user(args.owner_login)\

    if args.repo_name is not None:
        repos_to_check = (from_user.get_repo(args.repo_name), )
    else:
        repos_to_check = from_user.get_repos()

    for repo_to_check in repos_to_check:
        repo_check_default_branch(repo_to_check)


def repo_check_default_branch(repo):
    set_repo_versions = set(_version_from_branch(branch.name) for branch in repo.get_branches())
    set_repo_versions.discard(None)
    sorted_versions = list(set_repo_versions)
    sorted_versions.sort()

    messages = []

    if not sorted_versions:
        messages.append('no versions found')

    default_version = _version_from_branch(repo.default_branch)
    sorted_versions_releases = list(filter(lambda v: not v.is_prerelease, sorted_versions))
    versions_str = list(str(v) for v in sorted_versions)

    if default_version is None:
        messages.append('default branch is not a version')
    else:
        if default_version.is_prerelease:
            messages.append('version of default branch is a prerelease: default="{}" versions={}'.format(
                default_version, versions_str))

        try:
            default_version_index = sorted_versions.index(default_version)
            if default_version.is_prerelease:
                if default_version_index < len(sorted_versions) - 1:
                    messages.append('version of default branch out of date: default="{}" versions={}'.format(
                        default_version, versions_str))
            else:
                if default_version_index < len(sorted_versions_releases) - 1:
                    messages.append('version of default branch out of date: default="{}" versions={}'.format(
                        default_version, versions_str))
        except ValueError:
            messages.append('version of default branch not recognized')

    if messages:
        print('{}: {}'.format(repo.full_name, '; '.join(messages)))


def _version_from_branch(branch) -> typing.Optional[Version]:
    try:
        [_, v] = branch.split('/', 1)
    except ValueError:
        return None
    try:
        return Version(v)
    except InvalidVersion:
        return None


if __name__ == '__main__':
    main()
