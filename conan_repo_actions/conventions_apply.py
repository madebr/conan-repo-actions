#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
from collections import namedtuple
import enum
import git
from github.AuthenticatedUser import AuthenticatedUser
from github.Repository import Repository
from bincrafters_conventions.bincrafters_conventions import Command as BincraftersConventionsCommand
from conan_readme_generator.main import run as conan_readme_generator_run
from conan_repo_actions import NAME
from conan_repo_actions.util import Configuration, chargv, chdir, GithubUser
from conan_repo_actions.fork_create import fork_create
from conan_repo_actions.default_branch import ConanRepo
from pathlib import Path
import shutil
import typing


def main():
    parser = argparse.ArgumentParser(description='Apply bincrafters conventions, update readme and push to a remote')
    parser.add_argument('--owner_login', type=str, required=True, help='owner of the repo to clone')
    parser.add_argument('--keep_clone', action='store_true', help='do not remove already checked out repos')
    parser.add_argument('--git_wd', type=Path, default=None, help='path where to clone the repos to')
    parser.add_argument('--channel_suffix', type=str, default=generate_default_channel_suffix(),
                        help='suffix to append to the channel')
    argparse_add_which_branch_option(parser)
    parser.add_argument('repo_name', type=str, help='name of the repo')

    args = parser.parse_args()

    c = Configuration()
    g = c.get_github()

    from_user = g.get_user(args.owner_login)
    to_user = g.get_user()

    which_branch = argparse_calculate_branch(args.repo_name, args.branch_dest, from_user)
    if which_branch is None:
        print('No conan branch detected')
        return

    push_data = apply_scripts_and_push(args.repo_name, which_branch,
                                       from_user, to_user, c.git_wd, args.channel_suffix,
                                       args.keep_clone)
    if push_data is not None:
        print('Pushed changes to branch "{}" of "{}"'.format(push_data.to_branch, push_data.to_repo.full_name))
    else:
        print('Scripts did not change anything')


class WhichBranch(enum.Enum):
    DEFAULT = 0
    LATEST = 1
    LATEST_STABLE = 2
    LATEST_TESTING = 3


def argparse_add_which_branch_option(parser):
    branch_group = parser.add_mutually_exclusive_group()
    branch_group.add_argument('--default_branch', dest='branch_dest', action='store_const',
                              const=WhichBranch.DEFAULT, help='use default branch')
    branch_group.add_argument('--latest', dest='branch_dest', action='store_const',
                              const=WhichBranch.LATEST, help='use branch with the highest version')
    branch_group.add_argument('--latest_stable', dest='branch_dest', action='store_const',
                              const=WhichBranch.LATEST_STABLE, help='use branch of stable channel of highest version')
    branch_group.add_argument('--latest_testing', dest='branch_dest', action='store_const',
                              const=WhichBranch.LATEST_TESTING, help='use branch of testing channel of highest version')
    branch_group.add_argument('--branch', dest='branch_dest', help='use the most recent branch')
    parser.set_defaults(branch_dest=WhichBranch.DEFAULT)


def argparse_calculate_branch(repo_name: str, branch_dest: typing.Union[WhichBranch, str], from_user: GithubUser) -> typing.Optional[str]:
    from_repo = from_user.get_repo(repo_name)
    if branch_dest == WhichBranch.DEFAULT:
        return from_repo.default_branch
    elif branch_dest == WhichBranch.LATEST:
        conan_repo = ConanRepo.from_repo(from_repo)
        most_recent_version = conan_repo.most_recent_version_by_channel()
        if most_recent_version is None:
            return
        return next(conan_repo.get_branches_by_version(most_recent_version)).name
    elif branch_dest == WhichBranch.LATEST_STABLE:
        conan_repo = ConanRepo.from_repo(from_repo)
        most_recent_version = conan_repo.most_recent_version_by_channel('stable')
        if most_recent_version is None:
            return
        return next(conan_repo.get_branches_by_version(most_recent_version)).name
    elif branch_dest == WhichBranch.LATEST_TESTING:
        conan_repo = ConanRepo.from_repo(from_repo)
        most_recent_version = conan_repo.most_recent_version_by_channel('testing')
        if most_recent_version is None:
            return
        return next(conan_repo.get_branches_by_version(most_recent_version)).name
    else:
        return branch_dest


def generate_default_channel_suffix():
    return datetime.datetime.now().isoformat(timespec='seconds').translate(str.maketrans(':-', '__'))


ConventionsApplyResult = namedtuple('ConventionsApplyresult', ('from_repo', 'from_branch', 'to_repo', 'to_branch', ))


def apply_scripts_and_push(repo_name: str, from_branch: str,
                           from_user: GithubUser, to_user: AuthenticatedUser, git_wd: Path, channel_suffix: str,
                           keep_clone: bool=False) -> typing.Optional[ConventionsApplyResult]:

    from_repo, to_repo = fork_create(repo_name, from_user, to_user)

    remote_origin = 'origin'
    remote_user = 'user'

    git_repo_wd = git_wd / repo_name
    clone_repo(repo_name, keep_clone, git_wd, from_repo, to_repo, remote_origin, remote_user, from_branch)

    repo = git.Repo(git_repo_wd)

    updated = False

    def commit_changes(repo, message):
        nonlocal updated
        repo.git.add(all=True)
        if repo.is_dirty():
            repo.index.commit(message=message)
            updated = True

    print('Running bincrafters-conventions...')
    with chdir(git_repo_wd):
        cmd = BincraftersConventionsCommand()
        cmd.run(['--local', ])

    commit_changes(repo, 'Run bincrafters-conventions\n\ncommit by {}'.format(NAME))

    print('Running conan-readme-generator...')
    with chdir(git_repo_wd):
        with chargv(['']):
            conan_readme_generator_run()

    commit_changes(repo, 'Run conan-readme-generator\n\ncommit by {}'.format(NAME))

    def remote_branch_from_local(local):
        try:
            channel, version = local.split('/', 1)
            return '{}_{}/{}'.format(channel, channel_suffix, version)
        except ValueError:
            return '{}_{}'.format(local, channel_suffix)

    if updated:
        remote_branch_name = remote_branch_from_local(repo.active_branch.name)
        repo.remote(remote_user).push('{}:{}'.format(repo.active_branch.name, remote_branch_name))
        return ConventionsApplyResult(from_repo=from_repo, from_branch=from_branch, to_repo=to_repo, to_branch=remote_branch_name)
    else:
        return None


def clone_repo(repo_name, keep_clone, wd, from_repo, to_repo, remote_origin, remote_user, which_branch):
    git_repo_wd = wd / repo_name

    if git_repo_wd.exists():
        if not keep_clone:
            shutil.rmtree(git_repo_wd)

    if not git_repo_wd.exists():
        r = git.Repo.clone_from(url=from_repo.clone_url, to_path=git_repo_wd)
        r.remote('origin').rename(remote_origin)
        r.git.remote(['add', remote_user, to_repo.ssh_url])
        r.remote(remote_user).update()

    remote = 'origin'

    r = git.Repo(git_repo_wd)
    r.git.checkout('{}/{}'.format(remote, which_branch), B=which_branch, force=True, track=True)


if __name__ == '__main__':
    main()
