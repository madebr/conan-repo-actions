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
from conan_repo_actions.util import Configuration, chargv, chdir, GithubUser, input_ask_question_yn
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
    parser.add_argument('--interactive', action='store_true', help='interactive')
    parser.add_argument('--channel_suffix', default=generate_default_channel_suffix(),
                        help='suffix to append to the channel')
    argparse_add_which_branch_option(parser)
    argparse_add_what_conventions(parser)
    parser.add_argument('repo_name', type=str, help='name of the repo+branch. Format: REPO[:BRANCH]')

    args = parser.parse_args()

    c = Configuration()
    g = c.get_github()

    user_from = g.get_user(args.owner_login)
    user_to = g.get_user()

    repobranch_from = calculate_repo_branch(user=user_from, repo_branch_name=args.repo_name)

    push_data = apply_scripts_and_push2(repobranch_from=repobranch_from,
                                        user_to=user_to,
                                        git_wd=c.git_wd, channel_suffix=args.channel_suffix,
                                        run_conventions=args.apply_conventions, run_readme=args.apply_readme,
                                        keep_clone=args.keep_clone, interactive=args.interactive)

    if push_data is not None:
        print('Pushed changes to branch "{}" of "{}"'.format(push_data.branch_to, push_data.repo_to.full_name))
    else:
        print('Scripts did not change anything')


def argparse_add_what_conventions(parser: argparse.ArgumentParser):
    group = parser.add_argument_group()
    group.add_argument('--do-not-apply-readme', dest='apply_readme', action='store_false',
                       help='do not run readme generation script')
    group.add_argument('--do-not-apply-conventions', dest='apply_conventions', action='store_false',
                       help='do not run conventions script')


def argparse_add_which_branch_option(parser: argparse.ArgumentParser):
    group = parser.add_argument_group('Branch to use when none is specified')
    branch_group = group.add_mutually_exclusive_group()
    branch_group.add_argument('--default_branch', dest='branch_dest', action='store_const',
                              const=WhichBranch.DEFAULT, help='use default branch')
    branch_group.add_argument('--latest', dest='branch_dest', action='store_const',
                              const=WhichBranch.LATEST, help='use branch with highest version')
    branch_group.add_argument('--latest_stable', dest='branch_dest', action='store_const',
                              const=WhichBranch.LATEST_STABLE, help='use branch of stable channel with highest version')
    branch_group.add_argument('--latest_testing', dest='branch_dest', action='store_const',
                              const=WhichBranch.LATEST_TESTING,
                              help='use branch of testing channel with highest version')
    branch_group.add_argument('--branch', dest='branch_dest', help='use specified branch')
    parser.set_defaults(branch_dest=WhichBranch.DEFAULT)


def calculate_repo_branch(user: GithubUser, repo_branch_name: str) -> 'GithubRepoBranch':
    list_repo_branch = repo_branch_name.split(':', 1)
    if len(list_repo_branch) == 1:
        repo_str, branch = list_repo_branch[0], None
    else:
        repo_str, branch = list_repo_branch[0], list_repo_branch[1]
    repo = user.get_repo(repo_str)
    return GithubRepoBranch(repo, branch)


def calculate_branch(repo: Repository, branch_dest: typing.Union[WhichBranch, str]) -> typing.Optional[str]:
    if branch_dest == WhichBranch.DEFAULT:
        return repo.default_branch
    elif branch_dest == WhichBranch.LATEST:
        conan_repo = ConanRepo.from_repo(repo)
        most_recent_version = conan_repo.most_recent_version()
        if most_recent_version is None:
            return
        return next(conan_repo.get_branches_by_version(most_recent_version)).name
    elif branch_dest == WhichBranch.LATEST_STABLE:
        conan_repo = ConanRepo.from_repo(repo)
        most_recent_branch = conan_repo.most_recent_branch_by_channel('stable')
        if most_recent_branch is None:
            return
        return most_recent_branch.name
    elif branch_dest == WhichBranch.LATEST_TESTING:
        conan_repo = ConanRepo.from_repo(repo)
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
                           run_conventions: bool=True, run_readme: bool=True,
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

    if run_conventions:
        print('Running bincrafters-conventions...')
        with chdir(git_repo_wd):
            cmd = BincraftersConventionsCommand()
            cmd.run(['--local', ])

        commit_changes(repo, 'Run bincrafters-conventions\n\ncommit by {}'.format(NAME))

    if run_readme:
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


class GithubRepoBranch(object):
    def __init__(self, repo: typing.Optional[Repository]=None, branch: typing.Optional[str]=None):
        self.repo = repo
        self.branch = branch


def apply_scripts_and_push2(repobranch_from: GithubRepoBranch, user_to: AuthenticatedUser,
                            git_wd: Path, channel_suffix: str,
                            run_conventions: bool=True, run_readme: bool=True,
                            keep_clone: bool=False, interactive: bool=False) -> typing.Optional[ConventionsApplyResult]:
    apply_action = ConventionsApplyAction(repobranch_from=repobranch_from, user_to=user_to,
                                          wd=git_wd, channel_suffix=channel_suffix,
                                          run_conventions=run_conventions, run_readme=run_readme,
                                          keep_clone=keep_clone, interactive=interactive)

    apply_action.check()
    print(apply_action.description())
    apply_action.action()

    if apply_action.work_done:
        return ConventionsApplyResult(repo_from=repobranch_from.repo, branch_from=repobranch_from.branch,
                                      repo_to=apply_action.repo_to, branch_to=apply_action.branch_to,)


class ConventionsApplyAction(ActionBase):
    def __init__(self, repobranch_from: GithubRepoBranch, user_to: AuthenticatedUser,
                 wd: Path, channel_suffix: str=None, run_conventions: bool=True, run_readme: bool=True,
                 which_branch: typing.Union[WhichBranch, str]=WhichBranch.DEFAULT, keep_clone: bool=False,  interactive: bool=False):
        super().__init__()

        self._repo_branch_from = repobranch_from

        self._repo_to = None
        self._branch_to = None

        self._user_to = user_to

        self._wd = wd
        self._channel_suffix = channel_suffix if channel_suffix is None else generate_default_channel_suffix()

        self._which_branch = which_branch

        self._keep_clone = keep_clone
        self._interactive = interactive

        self._work_done = None

        self._run_conventions = run_conventions
        self._run_readme = run_readme

    def run_check(self):
        if self._repo_branch_from.repo is None:
            raise ActionInterrupted()
        if self._repo_branch_from.branch is None:
            self._repo_branch_from.branch = calculate_branch(self._repo_branch_from.repo, self._which_branch)
        if self._repo_branch_from.branch is None:
            raise ActionInterrupted('Unknown branch')
        if not any((self._run_conventions, self._run_readme, )):
            raise ActionInterrupted('Nothing to do...')

    def run_action(self):
        fork_action = ForkCreateAction(repo_from=self._repo_branch_from.repo, user_to=self._user_to, interactive=self._interactive)
        fork_action.action()

        self._repo_to = fork_action.repo_to

        clone_action = RepoCloneAction(repo_from=self._repo_branch_from.repo, repo_to=self._repo_to,
                                       wd=self._wd, keep_clone=self._keep_clone, branch=self._repo_branch_from.branch)
        clone_action.action()

        repo = git.Repo(clone_action.repo_wd)

        updated = False

        def commit_changes(repo, message):
            nonlocal updated
            repo.git.add(all=True)
            if repo.is_dirty():
                repo.index.commit(message=message)
                updated = True

        if self._run_conventions:
            if self._interactive:
                if not input_ask_question_yn('Run bincrafters-conventions script?', default=True):
                    raise ActionInterrupted()
            print('Running bincrafters-conventions...')
            with chdir(clone_action.repo_wd):
                cmd = BincraftersConventionsCommand()
                cmd.run(['--local', ])

            commit_changes(repo, 'Run bincrafters-conventions\n\ncommit by {}'.format(NAME))

        if self._run_readme:
            if self._interactive:
                if not input_ask_question_yn('Run conan-readme-generator script?', default=True):
                    raise ActionInterrupted()
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
            if self._interactive:
                from .util import editor_interactive_remove_comments
                branch_to = editor_interactive_remove_comments(
                    '{branch}\n\n# Enter the name of the remote branch (repo={repo})'.format(
                        branch=branch_to, repo=self._repo_to.full_name)).strip()
                if not branch_to or not input_ask_question_yn(
                        'Push changes to remote branch (user={user}) "{branch}"?'.format(
                            user=self._user_to.login, branch=branch_to), default=True):
                    raise ActionInterrupted()
            repo.remote(clone_action.repo_to_name).push('{}:{}'.format(repo.active_branch.name, branch_to))
            self._branch_to = branch_to
            self._work_done = True

    def run_description(self) -> str:
        return 'Fork, clone and run conventions on "{repo_from_name}"'.format(
            repo_from_name=self._repo_from.full_name,
        )

    @property
    def repo_from(self) -> Repository:
        return self._repo_branch_from.repo

    @property
    def branch_from(self) -> typing.Optional[str]:
        return self._repo_branch_from.branch

    @property
    def repo_to(self) -> typing.Optional[Repository]:
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
            self._branch = ConanRepo.from_repo(self._repo_from).select_branch(branch).name

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
        r.git.checkout('{}/{}'.format(self._name_from, self._branch), B=self._branch, force=True, track=True)

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
