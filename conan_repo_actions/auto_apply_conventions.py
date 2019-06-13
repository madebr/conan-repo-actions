#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
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


class WhichBranch(enum.Enum):
    DEFAULT = 0,
    MOST_RECENT = 1,


def main():
    parser = argparse.ArgumentParser(description='Apply bincrafters conventions, update readme and push to a remote')
    parser.add_argument('--owner_login', type=str, required=True, help='owner of the repo to clone')
    parser.add_argument('--keep_clone', action='store_true', help='do not remove already checked out repos')
    parser.add_argument('--git_wd', type=Path, default=None, help='path where to clone the repos to')
    branch_group = parser.add_mutually_exclusive_group()
    branch_group.add_argument('--default_branch', dest='branch_dest', action='store_const', const=WhichBranch.DEFAULT, help='use the default branch')
    branch_group.add_argument('--most_recent', dest='branch_dest', action='store_const', const=WhichBranch.MOST_RECENT, help='use the most recent branch')
    branch_group.add_argument('--branch', dest='branch_dest', help='use the most recent branch')
    parser.set_defaults(branch_dest=WhichBranch.DEFAULT)
    parser.add_argument('repo_name', type=str, help='name of repo')

    args = parser.parse_args()

    c = Configuration()
    g = c.get_github()

    from_user = g.get_user(args.owner_login)
    to_user = g.get_user()

    to_repo = to_user.get_repo(args.repo_name)
    if args.branch_dest == WhichBranch.DEFAULT:
        which_branch = to_repo.default_branch
    elif args.branch_dest == WhichBranch.MOST_RECENT:
        conan_repo = ConanRepo.from_repo(to_repo)
        most_recent_version = conan_repo.most_recent_version_by_channel()
        if most_recent_version is None:
            print('No conan branch detected')
            return
        which_branch = next(conan_repo.get_branches_by_version(most_recent_version)).name
    else:
        which_branch = args.branch_dest

    push_data = apply_scripts(args.repo_name, which_branch, from_user, to_user, c.git_wd, args.keep_clone)
    if push_data is not None:
        to_repo, remote_branch_name = push_data
        print('Pushed changes to branch "{}" of "{}"'.format(remote_branch_name, to_repo.full_name))
    else:
        print('Scripts did not change anything')


def apply_scripts(repo_name: str, which_branch: str, from_user: GithubUser,
                  to_user: AuthenticatedUser, git_wd: Path,
                  keep_clone: bool=False) -> typing.Optional[typing.Tuple[Repository, str]]:

    from_repo, to_repo = fork_create(repo_name, from_user, to_user)

    remote_origin = 'origin'
    remote_user = 'user'

    git_repo_wd = git_wd / repo_name
    clone_repo(repo_name, keep_clone, git_wd, from_repo, to_repo, remote_origin, remote_user, which_branch)

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
        suffix = datetime.datetime.now().isoformat(timespec='seconds').translate(str.maketrans(':-', '__'))
        try:
            channel, version = local.split('/', 1)
            return '{}_{}/{}'.format(channel, suffix, version)
        except ValueError:
            return '{}_{}'.format(local, suffix)

    if updated:
        remote_branch_name = remote_branch_from_local(repo.active_branch.name)
        repo.remote(remote_user).push('{}:{}'.format(repo.active_branch.name, remote_branch_name))
        return to_repo, remote_branch_name
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
