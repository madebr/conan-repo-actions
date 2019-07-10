#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path
import yaml
from .fetch_dependencies import repo_branch_dependencies
from .conventions_apply import argparse_add_which_branch_option, calculate_repo_branch, \
    calculate_branch, GithubRepoBranch
from .util import Configuration


def main():
    parser = argparse.ArgumentParser(description='Fetch dependencies of repo')
    parser.add_argument('--owner_login', type=str, required=True, help='owner of the repo to clone')
    parser.add_argument('--interactive', action='store_true', help='interactive')
    argparse_add_which_branch_option(parser)
    parser.add_argument('--output', '-o', type=Path, required=True,
                        help='directory where to store the dependency information')
    parser.add_argument('repo_names', type=str, nargs=argparse.ZERO_OR_MORE,
                        help='names of the repo+branch. Format: REPO[:BRANCH]')

    args = parser.parse_args()

    output: Path = args.output
    if not output.is_dir():
        output.mkdir(parents=True)

    c = Configuration()
    g = c.get_github()

    user_from = g.get_user(args.owner_login)

    repo_branches = []

    repo_names = args.repo_names
    if not repo_names:
        repos = user_from.get_repos()
        for repo in repos:
            repo_branch = GithubRepoBranch(repo=repo)
            repo_branch.branch = calculate_branch(repo=repo_branch.repo, branch_dest=args.branch_dest)
            if repo_branch.branch is None:
                print('Skipping repo:', repo.name, '(no branch found according to specs)')
                continue
            repo_branches.append(repo_branch)
    else:
        for repo_name in args.repo_names:
            repo_branch = calculate_repo_branch(user=user_from, repo_branch_name=repo_name)
            if repo_branch.branch is None:
                repo_branch.branch = calculate_branch(repo=repo_branch.repo, branch_dest=args.branch_dest)
            if repo_branch.branch is None:
                print('Skipping repo:', repo_branch.repo.name, '(no branch found according to specs)')
                continue
            repo_branches.append(repo_branch)

    for repo_branch in repo_branches:
        filename = output / (repo_branch.repo.name + '.yaml')
        if filename.exists():
            continue

        deps, version = repo_branch_dependencies(repo_branch)
        if version is None:
            print('Unable to get version of {}'.format(repo_branch.repo.name))
            version = 'unknown'

        data = {
            'name': repo_branch.repo.name,
            'version': version,
            'dependencies': list(d.reference for d in deps),
        }
        yaml.safe_dump(data, open(filename, 'w'))


if __name__ == '__main__':
    main()
