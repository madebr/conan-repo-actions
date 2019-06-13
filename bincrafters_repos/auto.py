#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import git
import github
from bincrafters_conventions.bincrafters_conventions import Command as BincraftersConventionsCommand
from conan_readme_generator.main import run as conan_readme_generator_run
from bincrafters_repos import GITHUB_BINCRAFTERS_NAME, GITHUB_TAG
from bincrafters_repos.util import Configuration, chargv, chdir
from bincrafters_repos.fork import create_fork
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner_login', type=str, default=GITHUB_BINCRAFTERS_NAME, help='owner of the repo to clone')
    parser.add_argument('--keep_clone', action='store_true', help='do not remove already checked out repos')
    parser.add_argument('--git_wd', type=Path, default=None, help='path where to clone the repos to')
    parser.add_argument('repo_name', type=str, help='name of repo')

    args = parser.parse_args()

    c = Configuration(git_wd=args.git_wd)
    l, p = c.github_login
    g = github.Github(l, p)

    from_user = g.get_user(args.owner_login)
    to_user = g.get_user()

    from_repo, to_repo = create_fork(args.repo_name, from_user, to_user)

    remote_origin = 'origin'
    remote_user = 'user'

    git_repo_wd = c.git_wd / args.repo_name
    clone_repo(args.repo_name, args.keep_clone, c.git_wd, from_repo, to_repo, remote_origin, remote_user)

    repo = git.Repo(git_repo_wd)

    updated = False

    def commit_changes(repo, message):
        nonlocal updated
        repo.git.add(all=True)
        if repo.is_dirty():
            repo.index.commit(message=message)
            updated = True

    with chdir(git_repo_wd):
        cmd = BincraftersConventionsCommand()
        cmd.run(['--local', ])

    commit_changes(repo, 'Run bincrafters-conventions\n\ncommit by {}'.format(GITHUB_TAG))

    with chdir(git_repo_wd):
        with chargv(['']):
            conan_readme_generator_run()

    commit_changes(repo, 'Run conan-readme-generator\n\ncommit by {}'.format(GITHUB_TAG))

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
        print('Pushed changes to branch "{}" of "{}"'.format(remote_branch_name, to_repo.full_name))


def clone_repo(repo_name, keep_clone, wd, from_repo, to_repo, remote_origin, remote_user):
    git_repo_wd = wd / repo_name

    if git_repo_wd.exists():
        if not keep_clone:
            shutil.rmtree(git_repo_wd)

    if not git_repo_wd.exists():
        r = git.Repo.clone_from(url=from_repo.clone_url, to_path=git_repo_wd)
        r.remote('origin').rename(remote_origin)
        r.git.remote(['add', remote_user, to_repo.ssh_url])
        r.remote(remote_user).update()


if __name__ == '__main__':
    main()
