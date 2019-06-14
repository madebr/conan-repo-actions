#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import github
from conan_repo_actions import NAME, WEBSITE
from conan_repo_actions.conventions_apply import apply_scripts_and_push, argparse_add_which_branch_option,\
    argparse_calculate_branch, generate_default_channel_suffix
from conan_repo_actions.util import Configuration
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Apply bincrafters conventions, update readme and push to a remote')
    parser.add_argument('--owner_login', type=str, required=True, help='owner of the repo to clone')
    parser.add_argument('--keep_clone', action='store_true', help='do not remove already checked out repos')
    parser.add_argument('--git_wd', type=Path, default=None, help='path where to clone the repos to')
    parser.add_argument('--channel_suffix', type=str, default=generate_default_channel_suffix(),
                        help='suffix to append to the channel')
    parser.add_argument('--issue_repo', type=str, help='repo where to post the summary to')
    parser.add_argument('--push_to_owner', action='store_true', help='repo where to post the summary to')
    argparse_add_which_branch_option(parser)
    parser.add_argument('repo_names', type=str, nargs=argparse.ONE_OR_MORE, help='names  of the repos')

    args = parser.parse_args()

    c = Configuration()
    g = c.get_github()

    from_user = g.get_user(args.owner_login)
    to_user = g.get_user()

    all_data = []
    error_repos = []

    if args.issue_repo:
        if args.push_to_owner:
            issue_repo = from_user.get_repo(args.issue_repo)
        else:
            issue_repo = to_user.get_repo(args.issue_repo)

    class PushData(object):
        push_data = None
        pull_number = None
        pull_repo = None

    for repo_name in args.repo_names:
        try:
            from_branch = argparse_calculate_branch(repo_name, args.branch_dest, from_user)
        except github.UnknownObjectException:
            print('Unknown repo: {}'.format(repo_name))
            error_repos.append(repo_name)
            continue
        if from_branch is None:
            print('Unknown repo: {}'.format(repo_name))
            error_repos.append(repo_name)
            continue
        o = PushData()
        o.push_data = apply_scripts_and_push(repo_name, from_branch,
                                             from_user, to_user, c.git_wd, args.channel_suffix,
                                             args.keep_clone)
        all_data.append(o)

    if not all_data:
        print('All repositories were already up to date. Nothing to do.')
        return

    for data in all_data:
        if args.push_to_owner:
            data.pull_repo = data.push_data.from_repo
        else:
            data.pull_repo = data.push_data.to_repo
        pull_title = 'Applied conventions on {}'.format(data.push_data.from_branch)
        pull_head = '{}:{}'.format(data.push_data.to_repo.owner.login, data.push_data.to_branch)
        pull_base = data.push_data.from_branch
        pull_body = '''Hello,

`bincrafters-conventions` and `conan-readme-generator` were executed on the branch {from_repo_branch}

###### auto-generated using [{script_name}]({script_url})'''.format(
            from_repo_branch=data.push_data.from_branch,
            script_name=NAME,
            script_url=WEBSITE,
        )
        pull = data.pull_repo.create_pull(title=pull_title, head=pull_head, base=pull_base, body=pull_body)
        data.pull_number = pull.number

    if args.issue_repo:
        all_names = ', '.join(o.push_data.from_repo.name for o in all_data)

        issue_title = 'Applied conventions on {}'.format(all_names)
        if len(issue_title) >= 80:
            issue_title = 'Applied conventions on {} repositories'.format(len(all_data))

        checkable_pull_info = []
        for data in all_data:
            checkable_pull_info.append('- [ ] {from_repo_name}: {from_repo_branch} {pull_slug}'.format(
                from_repo_name=data.push_data.from_repo.name,
                from_repo_branch=data.push_data.from_branch,
                pull_slug='{}/{}#{}'.format(data.pull_repo.owner.login,
                                            data.push_data.from_repo.name, data.pull_number),
            ))

        issue_body = '''Hello,
    
`bincrafters-conventions` and `conan-readme-generator` were executed on the following repositories:

{checkable_pull_info}

###### auto-generated using [{script_name}]({script_url})'''.format(
            checkable_pull_info='\n'.join(checkable_pull_info),
            script_name=NAME,
            script_url=WEBSITE,
        )

        issue = issue_repo.create_issue(
            title=issue_title,
            body=issue_body,
        )

        print('Created issue at {}'.format(issue.html_url))


if __name__ == '__main__':
    main()
