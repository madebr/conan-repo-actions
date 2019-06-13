#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import github
import github.Repository
from bincrafters_repos import GITHUB_TAG, GITHUB_BINCRAFTERS_NAME
from bincrafters_repos.util import Configuration, GithubUser, input_ask_question_yn
import sys
import typing
from distutils.util import strtobool


def main():
    parser = argparse.ArgumentParser(description='Remove forked repositories')
    parser.add_argument('--owner_login', type=str, default=GITHUB_BINCRAFTERS_NAME,
                        help='Login of the owner of the source of the forked repos')
    parser.add_argument('--no-tag', dest='tag', action='store_false', help='Do not require this tool\'s tag')
    parser.add_argument('--delete', dest='delete', action='store_true', help='Delete the forked repositories')
    parser.add_argument('--force', dest='force', action='store_true', help='Do not ask for confirmation')

    args = parser.parse_args()

    c = Configuration()
    l, p = c.github_login

    g = github.Github(l, p)
    from_user = g.get_user(args.owner_login)
    to_user = g.get_user()

    if from_user.id == to_user.id:
        print('Cannot remove forks of repos of myself')
        return

    repos = forked_repos(from_user, to_user)
    for from_repo, to_repo in repos:
        if args.tag:
            if GITHUB_TAG not in to_repo.get_topics():
                continue
        print('- {} -> {} ({})'.format(from_repo.full_name, to_repo.full_name, to_repo.html_url))
        if args.delete:
            if args.force:
                delete = True
            else:
                delete = input_ask_question_yn('Delete {}?'.format(to_repo.full_name), default=False)
            if delete:
                try:
                    to_repo.delete()
                    print('"{}" deleted successfully'.format(to_repo.full_name))
                except github.GithubException:
                    print('Failed to delete "{}"'.format(to_repo.full_name), file=sys.stderr)


def forked_repos(from_user: GithubUser, to_user: GithubUser) -> typing.Iterable[typing.Tuple[github.Repository.Repository, github.Repository.Repository]]:
    for from_repo in from_user.get_repos():
        for fork_repo in from_repo.get_forks():
            if fork_repo.owner.id == to_user.id:
                yield from_repo, fork_repo


if __name__ == '__main__':
    main()
