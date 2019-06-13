#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import github
import github.AuthenticatedUser
from bincrafters_repos import GITHUB_BINCRAFTERS_NAME, GITHUB_TAG
from bincrafters_repos.util import Configuration, GithubUser
import sys


def main():
    parser = argparse.ArgumentParser(description='Create a fork')
    parser.add_argument('--owner_login', type=str, default=GITHUB_BINCRAFTERS_NAME, help='owner of the repo to clone')
    parser.add_argument('repo_name', type=str, help='name of repo to clone')

    args = parser.parse_args()

    c = Configuration()
    l, p = c.github_login

    g = github.Github(l, p)
    from_user = g.get_user(args.owner_login)
    to_user = g.get_user()

    from_repo, new_repo = create_fork(args.repo_name, from_user, to_user)
    print(from_repo.owner.login, from_repo.clone_url, from_repo.ssh_url)
    print(new_repo.owner.login, new_repo.clone_url, new_repo.ssh_url)


def create_fork(repo_name: str, from_user: GithubUser, to_user: github.AuthenticatedUser.AuthenticatedUser):
    try:
        from_repo = from_user.get_repo(repo_name)
    except github.UnknownObjectException:
        raise Exception('Repo "{}" does not exist'.format(repo_name))
    for fork_repo in from_repo.get_forks():
        if fork_repo.owner.id == to_user.id:
            print('Repo "{}" already forked to "{}".'.format(from_repo.full_name, fork_repo.full_name), file=sys.stderr)
            return from_repo, fork_repo
    to_repo = to_user.create_fork(from_repo)
    new_name = "{}-{}".format(GITHUB_TAG, repo_name)
    to_repo.edit(name=new_name)
    to_repo.edit(has_issues=False, has_projects=False, has_wiki=False, private=False)
    from_topics = from_repo.get_topics()
    to_repo.replace_topics([GITHUB_TAG] + from_topics)
    return from_repo, to_repo


if __name__ == '__main__':
    main()
