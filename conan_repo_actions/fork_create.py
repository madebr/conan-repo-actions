#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import github
import github.AuthenticatedUser
from conan_repo_actions import FORK_PREFIX, FORK_TAG
from conan_repo_actions.util import Configuration, GithubUser
import sys


def main():
    parser = argparse.ArgumentParser(description='Create a fork')
    parser.add_argument('--owner_login', type=str, required=True, help='owner of the repo to clone')
    parser.add_argument('repo_name', type=str, help='name of repo to clone')

    args = parser.parse_args()

    c = Configuration()
    g = c.get_github()

    from_user = g.get_user(args.owner_login)
    to_user = g.get_user()

    from_repo, new_repo = fork_create(args.repo_name, from_user, to_user)
    print(from_repo.owner.login, from_repo.clone_url, from_repo.ssh_url)
    print(new_repo.owner.login, new_repo.clone_url, new_repo.ssh_url)


def fork_create(repo_name: str, from_user: GithubUser, to_user: github.AuthenticatedUser.AuthenticatedUser):
    try:
        from_repo = from_user.get_repo(repo_name)
    except github.UnknownObjectException:
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


if __name__ == '__main__':
    main()
