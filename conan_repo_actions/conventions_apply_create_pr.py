#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import github
from github.AuthenticatedUser import AuthenticatedUser
from github.Repository import Repository
from github.Issue import Issue
from github.PullRequest import PullRequest
from .base import ActionInterrupted, ActionBase
from .conventions_apply import GithubRepoBranch, apply_scripts_and_push, argparse_add_which_branch_option,\
    argparse_add_what_conventions, calculate_repo_branch, generate_default_channel_suffix, WhichBranch, \
    ConventionsApplyAction
from .fork_create import ForkCreateAction
from .util import input_ask_question_yn, editor_interactive
from conan_repo_actions.util import Configuration
from pathlib import Path
import typing


def main():
    parser = argparse.ArgumentParser(description='Apply bincrafters conventions, update readme and push to a remote')
    parser.add_argument('--owner_login', type=str, required=True, help='owner of the repo to clone')
    parser.add_argument('--keep_clone', action='store_true', help='do not remove already checked out repos')
    parser.add_argument('--git_wd', type=Path, default=None, help='path where to clone the repos to')
    parser.add_argument('--interactive', action='store_true', help='interactive')
    parser.add_argument('--channel_suffix', type=str, default=generate_default_channel_suffix(),
                        help='suffix to append to the channel')
    parser.add_argument('--repo_issue', required=True, help='repo where to post the summary to (format: [USER:]REPO)')
    parser.add_argument('--message', '-m', type=str, default=None, help='extra text message')
    parser.add_argument('--test', action='store_true', help='Create pr and issue to own forked repos')
    argparse_add_which_branch_option(parser)
    argparse_add_what_conventions(parser)
    parser.add_argument('repos', type=str, nargs=argparse.ONE_OR_MORE,
                        help='names of the repos. Format: REPO[:BRANCH]')

    args = parser.parse_args()

    c = Configuration()
    g = c.get_github()

    user_to = g.get_user()
    user_from = g.get_user(args.owner_login)

    repo_issue = repo_string_to_github_repo(g, args.repo_issue, args.owner_login)

    repobranches_from = []
    for repo_name in args.repos:
        try:
            repobranch_from = calculate_repo_branch(user=user_from, repo_branch_name=repo_name)
            repobranches_from.append(repobranch_from)
        except github.UnknownObjectException:
            print('Unknown repo: {}'.format(repo_name))
            raise

    action = ConventionsCreatePullAction(repobranches_from=repobranches_from, repo_issue=repo_issue, user_to=user_to,
                                         wd=c.git_wd, which_branch=args.branch_dest, channel_suffix=args.channel_suffix,
                                         extra_message=args.message,
                                         run_conventions=args.apply_conventions, run_readme=args.apply_readme,
                                         test=args.test, interactive=args.interactive)
    action.check()
    action.action()


def repo_string_to_github_repo(g: github.Github, repo_str: str, default_owner: str) -> Repository:
    try:
        [repo_issue_owner_str, repo_issue_name_str] = repo_str.split(':', 1)
        return g.get_user(repo_issue_owner_str).get_repo(repo_issue_name_str)
    except ValueError:
        return g.get_user(default_owner).get_repo(repo_str)


def list_to_readable_string(l: typing.List[typing.Any]) -> str:
    if len(l) > 1:
        return ', '.join(str(s) for s in l[:-1]) + ' and ' + str(l[-1])
    else:
        return str(l[0])


class ConventionsCreatePullAction(ActionBase):
    def __init__(self, user_to: AuthenticatedUser, repobranches_from: typing.Iterable[GithubRepoBranch],
                 repo_issue: Repository, wd: Path, which_branch: WhichBranch=WhichBranch.DEFAULT, channel_suffix: str=None,
                 extra_message: typing.Optional[str]=None, run_conventions: bool = True, run_readme: bool = True,
                 test: bool=False, interactive: bool=False):
        super().__init__(interactive=interactive)
        self._user_to = user_to

        self._repobranches_from = list(repobranches_from)

        self._repo_issue = repo_issue

        self._channel_suffix = channel_suffix

        self._wd = wd
        self._interactive = interactive

        self._which_branch = which_branch

        self._run_conventions = run_conventions
        self._run_readme = run_readme

        self._extra_message = extra_message if extra_message else ''

        self._conventions_actions: typing.Optional[typing.List[ConventionsApplyAction]] = None
        self._pulls : typing.Optional[typing.List[CreatePullAction]] = None
        self._issue: typing.Optional[CreateIssueAction] = None

        self._test = test

    def run_check(self):
        if self._conventions_actions is None:
            actions = []
            for repobranch_from in self._repobranches_from:
                actions.append(ConventionsApplyAction(repobranch_from=repobranch_from, user_to=self._user_to,
                                                      channel_suffix=self._channel_suffix, wd=self._wd,
                                                      run_conventions=self._run_conventions, run_readme=self._run_readme,
                                                      which_branch=self._which_branch, interactive=self._interactive))
            self._conventions_actions = actions

        for convention_action in self._conventions_actions:
            convention_action.check()

    def run_action(self):
        for convention_action in self._conventions_actions:
            convention_action.action()

        actual_convention_action = list(filter(lambda a: a.work_done, self._conventions_actions))
        if not actual_convention_action:
            raise ActionInterrupted('conventions did not modify anything. Aborting.')

        print('Conventions ran on {nb} repos: {repos}'.format(
            nb=len(actual_convention_action),
            repos = ', '.format(a.repo_from.full_name for a in actual_convention_action)
        ))

        what_run_list = []
        if self._run_conventions:
            what_run_list.append('`bincrafters-conventions`')
        if self._run_readme:
            what_run_list.append('`conan-readme-generator`')

        pulls = []
        for convention_action in actual_convention_action:
            # repo_from and repo_to must be switched here
            repo_pull_from = convention_action.repo_to
            branch_pull_from = convention_action.branch_to
            repo_pull_to = convention_action.repo_from
            branch_pull_to = convention_action.branch_from
            if self._test:
                repo_pull_to = convention_action.repo_to

            title = 'Applied conventions on {}'.format(convention_action.branch_from)
            body = 'Hello,\n' \
                   '\n' \
                   '{what_run_str} was executed on the branch {branch_pull_to}\n' \
                   '\n{extra_message}'.format(
                branch_pull_to=branch_pull_to,
                what_run_str=list_to_readable_string(what_run_list),
                extra_message=self._extra_message,
            )

            pull = CreatePullAction(repo_to=repo_pull_to, branch_to=branch_pull_to, repo_from=repo_pull_from, branch_from=branch_pull_from,
                              title=title, body=body, data=convention_action, interactive=self.interactive)
            pull.action()

            pulls.append(pull)

        self._pulls = pulls

        checkable_pull_info = []
        for pull in self._pulls:
            conv: ConventionsApplyAction = pull.data
            checkable_pull_info.append('- [ ] {repo_from_name}: {repo_from_branch} {pull_slug}'.format(
                repo_from_name=conv.repo_from.name,
                repo_from_branch=conv.branch_from,
                pull_slug='{}#{}'.format(conv.repo_to.full_name if self._test else conv.repo_from.full_name,
                                         pull.pr.number
                                         )
            ))
        checkable_pull_text = '\n'.join(checkable_pull_info)

        repo_issue = self._repo_issue
        if self._test:
            fork_repo_issue_action = ForkCreateAction(repo_from=self._repo_issue, user_to=self._user_to,
                                               interactive=self.interactive)
            fork_repo_issue_action.action()
            repo_issue = fork_repo_issue_action.repo_to

        names = ', '.join(a.repo_from.name for a in self._conventions_actions)
        title = 'Applied conventions on {}'.format(names)
        if len(title) >= 80:
            title = 'Applied conventions on {} repositories'.format(len(self._pulls))
        body = 'Hello,\n' \
               '\n' \
               '{what_run_str} was executed on the following repositories:\n' \
               '\n' \
               '{checkable_pull_text}\n' \
               '\n' \
               '{extra_message}'.format(
            what_run_str=list_to_readable_string(what_run_list),
            checkable_pull_text=checkable_pull_text,
            extra_message=self._extra_message,
        )

        self._issue = CreateIssueAction(repo=repo_issue, title=title, body=body, data=self._pulls,
                                        interactive=self.interactive)
        self._issue.action()


    @property
    def pulls(self):
        return self._pulls


class CreatePullAction(ActionBase):
    def __init__(self, repo_to: Repository, branch_to: str, repo_from: Repository, branch_from: str, title: str,
                 body: str, data: typing.Any=None, interactive: bool=False):
        super().__init__(interactive=interactive)
        self._repo_to = repo_to
        self._branch_to = branch_to

        self._repo_from = repo_from
        self._branch_from = branch_from

        self._title = title
        self._body = body

        self._data = data

        self._pr: typing.Optional[PullRequest] = None

    def run_check(self):
        pass

    def run_action(self):
        head = '{}:{}'.format(self._repo_from.owner.login, self._branch_from)
        base = self._branch_to

        body = self._body
        if self.interactive:
            answer = input_ask_question_yn('Create pull request at repo "{repo_to}", '
                                           'from repo "{repo_from}" ("{branch_from}->{branch_to}) with title "{title}"?'.format(
                repo_to=self._repo_to.full_name,
                repo_from=self._repo_from.full_name,
                branch_from=self._branch_from,
                branch_to=self._branch_to,
                head=head,
                title=self._title,
            ))
            if input_ask_question_yn('Modify pull request body?', default=True):
                body = editor_interactive(body)
            if not answer:
                raise ActionInterrupted()

        self._pr = self._repo_to.create_pull(head=head, base=base, title=self._title, body=body)

        print('Created pull request at {}'.format(self._pr.html_url))

    @property
    def pr(self) -> typing.Optional[PullRequest]:
        return self._pr

    @property
    def data(self) -> typing.Any:
        return self._data


class CreateIssueAction(ActionBase):
    def __init__(self, repo: Repository, title: str, body: str, data: typing.Any=None, interactive: bool=False):
        super().__init__(interactive=interactive)
        self._repo = repo

        self._title = title
        self._body = body

        self._data = data

        self._issue: typing.Optional[Issue] = None

    def run_check(self):
        pass

    def run_action(self):
        body = self._body
        if self.interactive:
            answer = input_ask_question_yn('Create issue at repo "{repo_to}" with title "{title}"?'.format(
                repo_to=self._repo.full_name,
                title=self._title,
            ))
            if not answer:
                raise ActionInterrupted()
            if input_ask_question_yn('Modify pull request body?', default=True):
                body = editor_interactive(body)

        self._issue = self._repo.create_issue(
            title=self._title,
            body=body,
        )
        print('Created issue at {}'.format(self._issue.html_url))

    @property
    def issue(self) -> typing.Optional[Issue]:
        return self._issue

    @property
    def data(self) -> typing.Any:
        return self._data


if __name__ == '__main__':
    main()
