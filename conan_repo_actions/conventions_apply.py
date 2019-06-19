#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
from collections import namedtuple
import git
from github.AuthenticatedUser import AuthenticatedUser
from github.Repository import Repository
from bincrafters_conventions.bincrafters_conventions import Command as BincraftersConventionsCommand
from conan_readme_generator.main import run as conan_readme_generator_run
from conan_repo_actions import NAME
from conan_repo_actions.base import ActionBase, ActionInterrupted
from conan_repo_actions.default_branch import WhichBranch
from conan_repo_actions.util import Configuration, chargv, chdir, GithubUser
from conan_repo_actions.fork_create import fork_create, ForkCreateAction
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

    push_data = apply_scripts_and_push2(repo_name=args.repo_name, branch_from=which_branch,
                                        user_from=from_user, user_to=to_user,
                                        git_wd=c.git_wd, channel_suffix=args.channel_suffix,
                                        keep_clone=args.keep_clone)

    if push_data is not None:
        print('Pushed changes to branch "{}" of "{}"'.format(push_data.branch_to, push_data.repo_to.full_name))
    else:
        print('Scripts did not change anything')


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
        most_recent_version = conan_repo.most_recent_version()
        if most_recent_version is None:
            return
        return next(conan_repo.get_branches_by_version(most_recent_version)).name
    elif branch_dest == WhichBranch.LATEST_STABLE:
        conan_repo = ConanRepo.from_repo(from_repo)
        most_recent_branch = conan_repo.most_recent_branch_by_channel('stable')
        if most_recent_branch is None:
            return
        return most_recent_branch.name
    elif branch_dest == WhichBranch.LATEST_TESTING:
        conan_repo = ConanRepo.from_repo(from_repo)
        most_recent_branch = conan_repo.most_recent_branch_by_channel('testing')
        if most_recent_branch is None:
            return
        return most_recent_branch.name
    else:
        return branch_dest


def generate_default_channel_suffix():
    return datetime.datetime.now().isoformat(timespec='seconds').translate(str.maketrans(':-', '__'))


ConventionsApplyResult = namedtuple('ConventionsApplyresult', ('repo_from', 'branch_from', 'repo_to', 'branch_to', ))


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


def apply_scripts_and_push2(repo_name: str, branch_from: str,
                            user_from: GithubUser, user_to: AuthenticatedUser, git_wd: Path, channel_suffix: str,
                            keep_clone: bool=False) -> typing.Optional[ConventionsApplyResult]:
    repo_from = user_from.get_repo(repo_name)
    apply_action = ConventionsApplyAction(repo_from=repo_from, branch_from=branch_from, user_to=user_to,
                                          wd=git_wd, channel_suffix=channel_suffix, keep_clone=keep_clone)

    apply_action.check()
    print(apply_action.description())
    apply_action.action()

    if apply_action.work_done:
        return ConventionsApplyResult(repo_from=repo_from, branch_from=branch_from,
                                      repo_to=apply_action.repo_to, branch_to=apply_action.branch_to)


class ConventionsApplyAction(ActionBase):
    def __init__(self, repo_from: Repository, branch_from: str, user_to: AuthenticatedUser, wd: Path,
                 channel_suffix: str, branch: typing.Union[str, WhichBranch]=WhichBranch.DEFAULT,
                 keep_clone: bool=False, interactive: bool=False):
        super().__init__()

        self._repo_from = repo_from
        self._branch_from = branch_from

        self._repo_to = None
        self._branch_to = None

        self._user_to = user_to

        self._wd = wd
        self._channel_suffix = channel_suffix

        self._branch = branch

        self._keep_clone = keep_clone
        self._interactive=interactive

        self._work_done = None

    def run_check(self):
        pass

    def run_action(self):
        fork_action = ForkCreateAction(repo_from=self._repo_from, user_to=self._user_to, interactive=self._interactive)
        fork_action.action()

        self._repo_to = fork_action.repo_to

        clone_action = RepoCloneAction(repo_from=self._repo_from, repo_to=self._repo_to,
                                       wd=self._wd, keep_clone=self._keep_clone, branch=self._branch)
        clone_action.action()

        repo = git.Repo(clone_action.repo_wd)

        updated = False

        def commit_changes(repo, message):
            nonlocal updated
            repo.git.add(all=True)
            if repo.is_dirty():
                repo.index.commit(message=message)
                updated = True

        print('Running bincrafters-conventions...')
        with chdir(clone_action.repo_wd):
            cmd = BincraftersConventionsCommand()
            cmd.run(['--local', ])

        commit_changes(repo, 'Run bincrafters-conventions\n\ncommit by {}'.format(NAME))

        print('Running conan-readme-generator...')
        with chdir(clone_action.repo_wd):
            with chargv(['']):
                conan_readme_generator_run()

        commit_changes(repo, 'Run conan-readme-generator\n\ncommit by {}'.format(NAME))

        def remote_branch_from_local(local):
            try:
                channel, version = local.split('/', 1)
                return '{}_{}/{}'.format(channel, self._channel_suffix, version)
            except ValueError:
                return '{}_{}'.format(local, self._channel_suffix)

        self._work_done = False
        if updated:
            branch_to = remote_branch_from_local(repo.active_branch.name)
            repo.remote(clone_action.repo_to_name).push('{}:{}'.format(repo.active_branch.name, branch_to))
            self._branch_to = branch_to
            self._work_done = True

    def description(self):
        return 'Fork, clone and run conventions on "{repo_from_name}"'.format(
            repo_from_name=self._repo_from.full_name,
        )

    @property
    def repo_to(self) -> Repository:
        return self._repo_to

    @property
    def branch_to(self) -> typing.Optional[str]:
        return self._branch_to

    @property
    def work_done(self) -> typing.Optional[bool]:
        return self._work_done


class RepoCloneAction(ActionBase):
    def __init__(self, repo_from: Repository, repo_to: Repository, wd: Path, keep_clone: bool=False,
                 name_from: str='origin', name_to: str='user', branch: typing.Union[str, WhichBranch]=WhichBranch.DEFAULT):
        super().__init__()
        self._repo_from = repo_from
        self._repo_to = repo_to

        self._wd = wd
        self._repo_wd = wd / repo_from.name

        self._keep_clone = keep_clone

        self._name_from = name_from
        self._name_to = name_to

        if isinstance(branch, str):
            self._branch = branch
        else:
            self._branch = ConanRepo.from_repo(self._repo_from).select_branch(branch)

    def run_check(self):
        assert self._wd.is_dir()

    def run_action(self):
        if self._repo_wd.exists():
            if not self._keep_clone:
                shutil.rmtree(self._repo_wd)

        if not self._repo_wd.exists():
            r = git.Repo.clone_from(url=self._repo_from.clone_url, to_path=self._repo_wd)
            r.remote('origin').rename(self._name_from)
            r.git.remote(['add', self._name_to, self._repo_to.ssh_url])
            r.remote(self._name_to).update()

        r = git.Repo(self._repo_wd)
        r.git.checkout('{}/{}'.format(self._name_from, self._branch.name), B=self._branch.name, force=True, track=True)

    def run_description(self):
        return 'Clone remote repository "{name_remote}" ({url_remote}) to local directory "{path_local}". ' \
               'Checkout "{branch_local}".'.format(
            name_remote=self._repo_from.full_name,
            url_remote=self._repo_from.clone_url,
            path_local=self._repo_wd,
            branch_local=self._branch,
        )

    @property
    def repo_wd(self) -> Path:
        return self._repo_wd

    @property
    def repo_from_name(self) -> str:
        return self._name_from

    @property
    def repo_to_name(self) -> str:
        return self._name_to


# def clone_repo(repo_name, keep_clone, wd, from_repo, to_repo, remote_origin, remote_user, which_branch):
#     git_repo_wd = wd / repo_name
#
#     if git_repo_wd.exists():
#         if not keep_clone:
#             shutil.rmtree(git_repo_wd)
#
#     if not git_repo_wd.exists():
#         r = git.Repo.clone_from(url=from_repo.clone_url, to_path=git_repo_wd)
#         r.remote('origin').rename(remote_origin)
#         r.git.remote(['add', remote_user, to_repo.ssh_url])
#         r.remote(remote_user).update()
#
#     remote = 'origin'
#
#     r = git.Repo(git_repo_wd)
#     r.git.checkout('{}/{}'.format(remote, which_branch), B=which_branch, force=True, track=True)


if __name__ == '__main__':
    main()
