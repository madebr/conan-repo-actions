#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from .util import Configuration, input_ask_question_yn
import travis
import typing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--interactive', action='store_true', help='interactive')
    args = parser.parse_args()

    c = Configuration()

    travis_org = travis.Travis.github_auth(c.github_token)
    travis_com = travis.Travis(token=c.travisci_com_token, base_url=travis.PRIVATE)

    cancel_all_builds((travis_com, travis_org,), interactive=args.interactive)


def cancel_all_builds(l_travis: typing.Iterable[travis.Travis], interactive: bool=False):
    for t in l_travis:
        user = t.get_user()
        for build in user.get_builds(active=True):
            if interactive:
                name = '{}#{}'.format(build.repository.name, build.number)
                if not input_ask_question_yn('Cancel build {}?'.format(name), default=True):
                    print('Skipping...')
                    continue
                print('Cancelling...')
            build.cancel()


if __name__ == '__main__':
    main()
