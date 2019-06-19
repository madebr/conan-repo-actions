#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import github
import github.Repository
from conan_repo_actions import FORK_TAG
from conan_repo_actions.base import ActionBase, ActionInterrupted
from conan_repo_actions.util import Configuration, GithubUser, input_ask_question_yn
import sys
import typing


def main():
    parser = argparse.ArgumentParser(description='List and optionally remove forked repositories')
    parser.add_argument('--owner_login', type=str, required=True,
                        help='Login of the owner of the source of the forked repos')
    tag_group = parser.add_mutually_exclusive_group()
    tag_group.add_argument('--no-tag', dest='do_tag', action='store_false', help='Do not require this tool\'s tag')
    tag_group.add_argument('--tag', dest='tag_name', default=FORK_TAG,
                           help='Name of the tag. (default="{}")'.format(FORK_TAG))
    parser.add_argument('--force', dest='interactive', action='store_false', help='interactive')
    parser.add_argument('--delete', dest='delete', action='store_true', help='Delete the forked repositories')

    args = parser.parse_args()

    fork_tag = args.tag_name if args.do_tag else None

    c = Configuration()
    g = c.get_github()

    user = g.get_user()
    user_from = g.get_user(args.owner_login)

    fork_cleanup(user=user, user_from=user_from, fork_tag=fork_tag, delete=args.delete, interactive=args.interactive)


def fork_cleanup(user: GithubUser, user_from: GithubUser, fork_tag: typing.Optional[str]=FORK_TAG,
                 delete: bool=False, interactive: bool=False):
    cleanup_action = ForkCleanupAction(user=user, user_from=user_from, fork_tag=fork_tag,
                                       delete=delete, interactive=interactive)
    cleanup_action.check()

    print(cleanup_action.description())

    cleanup_action.action()


class ForkCleanupAction(ActionBase):
    def __init__(self, user: GithubUser, user_from: GithubUser, fork_tag: typing.Optional[str]=FORK_TAG,
                 delete: bool=False, interactive: bool=False, progress: bool=True):
        super().__init__(interactive=interactive)
        self._user = user
        self._user_from = user_from
        self._fork_tag = fork_tag

        self._delete = delete

        self._forks = None

        self._progress = progress

    def run_check(self):
        if self._user_from.id == self._user.id:
            print('Cannot have forks of repos of myself', file=sys.stderr)
            raise ActionInterrupted()
        forks = []
        for repo_from, repo_to in self._repos_forked_iter():
            if self._fork_tag and self._fork_tag not in repo_to.get_topics():
                continue
            forks.append((repo_from, repo_to, ))
        self._forks = forks

    def _repos_forked_iter(self) -> \
            typing.Iterable[typing.Tuple[github.Repository.Repository, github.Repository.Repository]]:
        for repo_from in self._user_from.get_repos():
            for repo_fork in repo_from.get_forks():
                if self._progress:
                    print('.', end='', file=sys.stderr, flush=True)
                if repo_fork.owner.id == self._user.id:
                    yield repo_from, repo_fork
        if self._progress:
            print(file=sys.stderr)

    def run_action(self):
        for repo_from, repo_to in self._forks:
            print('- {} -> {} ({})'.format(repo_from.full_name, repo_to.full_name, repo_to.html_url))
            if self._delete:
                if self.interactive and not input_ask_question_yn('Delete {}?'.format(
                        repo_to.full_name), default=False):
                    continue
                try:
                    repo_to.delete()
                    print('"{}" deleted successfully'.format(repo_to.full_name))
                except github.GithubException:
                    print('Failed to delete "{}"'.format(repo_to.full_name), file=sys.stderr)

    def run_description(self) -> str:
        return 'Handling forks with parent user "{}" and child user "{}". {} repos found. Action:"{}"'.format(
            self._user_from,
            self._user,
            'NA' if self._forks is None else len(self._forks),
            'delete' if self._delete else 'list',
        )

    def run_sub_actions(self) -> typing.Iterable[ActionBase]:
        return ()


if __name__ == '__main__':
    main()
