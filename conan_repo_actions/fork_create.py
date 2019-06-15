#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from github import Github, GithubException
from github.AuthenticatedUser import AuthenticatedUser
from github.Repository import Repository
from conan_repo_actions import FORK_PREFIX, FORK_TAG
from conan_repo_actions.base import ActionBase
from conan_repo_actions.util import Configuration, GithubUser
import sys
import typing


def main():
    parser = argparse.ArgumentParser(description='Create a fork')
    parser.add_argument('--owner_login', type=str, required=True, help='owner of the repo to clone')
    parser.add_argument('repo_name', type=str, help='name of repo to clone')

    args = parser.parse_args()

    c = Configuration()
    g = c.get_github()

    repo_from, repo_to = fork_create2(g=g, user_from_name=args.owner_login, user_to_name=None, repo_from_name=args.repo_name)

    print('parent:', repo_from.full_name, repo_from.clone_url, repo_from.ssh_url)
    print('fork:', repo_to.full_name, repo_to.clone_url, repo_to.ssh_url)


def fork_create(repo_name: str, from_user: GithubUser, to_user: AuthenticatedUser):
    print('!!!!DEPRECATED!!!!', file=sys.stderr)
    try:
        from_repo = from_user.get_repo(repo_name)
    except GithubException:
        raise Exception('Repo "{}" does not exist'.format(repo_name))
    for fork_repo in from_repo.get_forks():
        if fork_repo.owner.id == to_user.id:
            print('Repo "{}" already forked to "{}".'.format(from_repo.full_name, fork_repo.full_name), file=sys.stderr)
            return from_repo, fork_repo
    to_repo = to_user.create_fork(from_repo)
    new_name = "{}-{}".format(FORK_PREFIX, repo_name)
    to_repo.edit(name=new_name)
    to_repo.edit(has_issues=False, has_projects=False, has_wiki=False, private=False)
    from_topics = from_repo.get_topics()
    to_repo.replace_topics([FORK_TAG] + from_topics)
    return from_repo, to_repo


def fork_create2(g: Github, repo_from_name: str, user_from_name: str, user_to_name: typing.Optional[str]=None):
    user_from = g.get_user(user_from_name)
    if not user_to_name:
        user_to = g.get_user()
    else:
        user_to = g.get_user(user_to_name)

    fork_action = ForkCreateAction(user_from=user_from, user_to=user_to, repo_from_name=repo_from_name)
    fork_action.check()
    fork_action.action()

    return fork_action.repo_from, fork_action.repo_to


class ForkCreateAction(ActionBase):
    def __init__(self, user_from: GithubUser, user_to: AuthenticatedUser, repo_from_name: str,
                 repo_to_name: typing.Optional[str]=None,
                 fork_tag: typing.Optional[str]=FORK_TAG, fork_prefix: typing.Optional[str]=FORK_PREFIX):
        super().__init__()
        self._user_from = user_from
        self._user_to = user_to

        self._repo_from_name = repo_from_name
        self._repo_from = None

        self._repo_to_name = repo_to_name
        self._repo_to = None

        self._fork_tag = fork_tag
        self._fork_prefix = fork_prefix

    def run_check(self):
        try:
            self._repo_from = self._user_from.get_repo(self._repo_from_name)
        except GithubException:
            raise Exception('Repo "{}" does not exist'.format(self._repo_from_name))

        for repo_fork in self._repo_from.get_forks():
            if repo_fork.owner.id == self._user_to.id:
                print('Repo "{}" already forked to "{}".'.format(self._repo_from.full_name, repo_fork.full_name), file=sys.stderr)
                self._repo_to = repo_fork
                self._repo_to_name = repo_fork.name
                break

        if not self._repo_to_name:
            if self._fork_prefix is None:
                self._repo_to_name = self._repo_from_name
            else:
                self._repo_to_name = '{}-{}'.format(self._fork_prefix, self._repo_from_name)

    def run_action(self):
        if self._repo_to is not None:
            return

        self._repo_to = self._user_to.create_fork(self._repo_from)
        self._repo_to.edit(name=self._repo_to_name)
        self._repo_to.edit()
        if self._fork_tag:
            topics_from = self._repo_from.get_topics()
            self._repo_to.replace_topics([self._fork_tag] + topics_from)

    def run_description(self) -> str:
        return 'Fork "{}/{}" to "{}/{}". (name of fork may be different)'.format(
            self._user_from.login,
            self._repo_from_name,
            self._user_to.login,
            self._repo_to_name,
        )

    def run_sub_actions(self) -> typing.Iterable[ActionBase]:
        return ()

    @property
    def repo_from(self) -> typing.Optional[Repository]:
        return self._repo_from

    @property
    def repo_to(self) -> typing.Optional[Repository]:
        return self._repo_to


if __name__ == '__main__':
    main()
