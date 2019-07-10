# -*- coding: utf-8 -*-

from . import __name__
import contextlib
import github
import itertools
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import typing
import yaml

GithubUser = typing.Union['github.AuthenticatedUser.AuthenticatedUser', 'github.NamedUser.NamedUser', ]


def input_ask_question_yn(question: str, default: typing.Optional[bool]=None) -> typing.Optional[bool]:
    y = 'y'
    n = 'n'

    if default in (True, ):
        y = 'Y'
    elif default in (False, ):
        n = 'N'

    msg = '{} [{}/{}] '.format(question, y, n)
    answer = input(msg)
    if answer == '' and default is not None:
        return default
    return _strtobool(answer)


def input_ask_question_options(question: str, options: typing.List[str],
                               default: typing.Any=None) -> typing.Union[int, typing.Any]:
    max_value = len(options) - 1
    if max_value < 0:
        raise ValueError('Option list cannot be empty')
    print(question)
    for option_i, option in enumerate(options):
        print('[{: 4}] {}'.format(option_i, option))
    msg = '{} [0-{}] '.format(question, max_value)
    answer = input(msg)
    if answer == '':
        return default
    if not answer.isdigit():
        raise ValueError('answer must be an integer')
    option = int(answer)
    if option < 0 or option > max_value:
        raise ValueError('answer out of range')
    return option


def _strtobool(answer: str) -> bool:
    answer = answer.lower()
    if answer in ('y', '1', 'true', ):
        return True
    elif answer in ('n', '0', 'false', ):
        return False
    raise ValueError('Not a boolean value: {}'.format(answer), answer)


EDITOR_ALTERNATIVES = [
    'vim',
    'vi',
    'nano',
    'emacs',
]


def _editor_search() -> typing.Optional[str]:
    editor = os.environ.get('EDITOR', None)
    for editor in itertools.chain((editor, ), EDITOR_ALTERNATIVES):
        if editor is None:
            continue
        path = shutil.which(editor)
        if path is not None:
            return path
    return None


def editor_interactive(initial_message: typing.Optional[str]=None) -> str:
    editor = _editor_search()
    if editor is None:
        raise RuntimeError('Cannot find text editor')

    initial_message = initial_message or ''
    with tempfile.NamedTemporaryFile(suffix='.tmp') as f:
        f.write(initial_message.encode())
        f.flush()
        subprocess.check_call([editor, f.name])
        f.seek(0)
        return f.read().decode()


def editor_interactive_remove_comments(initial_message: typing.Optional[str]=None) -> str:
    text = editor_interactive(initial_message)
    return '\n'.join(line for line in text.splitlines() if (line and not line.startswith('#')))


@contextlib.contextmanager
def chdir(newdir: Path):
    ''' Change directory using locked scope

    :param newdir: Temporary folder to move
    '''
    old_path = Path.cwd()
    os.chdir(str(newdir))
    try:
        yield
    finally:
        os.chdir(str(old_path))


@contextlib.contextmanager
def chargv(new_argv: typing.List[str]):
    ''' Change argv using locked scope

    :param new_argv: Temporary arguments to use
    '''
    old_argv = sys.argv
    sys.argv = new_argv
    try:
        yield
    finally:
        sys.argv = old_argv


class Configuration(object):
    __CWD = Path()

    def __init__(self,
                 github_token: typing.Optional[str]=None,
                 travisci_com_token: typing.Optional[str]=None,
                 git_wd: typing.Optional[Path]=None,
                 ):
        c = self.load_config()
        self._github_token = github_token or self._get_github_login_data(c)
        self._travisci_com_token = travisci_com_token or self._get_travisci_login_data(c)
        self._git_wd = git_wd or self._get_git_working_directories(c)

    @classmethod
    def default_config_folder(cls) -> Path:
        '''Returns data and configuration directory'''
        def get_config_parent() -> Path:
            xdg_home_config = os.environ.get('XDG_HOME_CONFIG')
            if xdg_home_config is not None:
                return Path(xdg_home_config)
            home = Path.home()
            return home / '.config'
        config_folder = os.environ.get('CONAN_REPO_ACTIONS_SETTINGS_PATH')
        if config_folder is not None:
            return Path(config_folder)
        return get_config_parent() / __name__

    @property
    def config_file_path(self) -> Path:
        folder = self.default_config_folder()
        folder.mkdir(exist_ok=True)
        return self.default_config_folder() / 'config.yml'

    def load_config(self):
        self.config_file_path.touch()
        c = yaml.safe_load(self.config_file_path.open())
        if c is None:
            c = {}
        if not isinstance(c, dict):
            raise RuntimeError('Error loading config file {}'.format(self.config_file_path))
        return c

    @property
    def github_token(self) -> typing.Optional[str]:
        return self._github_token

    def get_github(self) -> github.Github:
        t = self.github_token
        return github.Github(t)

    @classmethod
    def _get_github_login_data(cls, c) -> typing.Tuple[typing.Optional[str], typing.Optional[str]]:
        def _from_env() -> typing.Optional[str]:
            login = os.environ.get('CONAN_REPO_ACTIONS_GITHUB_LOGIN', '').strip()
            if not login:
                return None
            return login

        def _from_config() -> typing.Optional[str]:
            try:
                return c['github.com']['token']
            except KeyError:
                pass
        data = _from_env()
        if data is not None:
            return data
        data = _from_config()
        if data is not None:
            return data
        return None, None

    @property
    def travisci_com_token(self) -> typing.Optional[str]:
        return self._travisci_com_token

    @classmethod
    def _get_travisci_login_data(cls, c) -> typing.Tuple[typing.Optional[str], typing.Optional[str]]:
        def _from_env() -> typing.Optional[str]:
            login = os.environ.get('CONAN_REPO_ACTIONS_TRAVIS_LOGIN', '').strip()
            if not login:
                return None
            return login

        def _from_config() -> typing.Optional[str]:
            try:
                return c['travis-ci.com']['token']
            except KeyError:
                pass
        data = _from_env()
        if data is not None:
            return data
        data = _from_config()
        if data is not None:
            return data
        return None, None

    @classmethod
    def _get_git_working_directories(cls, c) -> typing.Optional[Path]:
        def _from_env() -> typing.Optional[Path]:
            p = os.environ.get('CONAN_REPO_ACTIONS_GIT_WD')
            if not p:
                return None
            p = Path(p)
            if not p.is_dir():
                return None
            return p

        def _from_config() -> typing.Optional[Path]:
            try:
                p = c['git_wd']
            except KeyError:
                return None
            p = Path(str(p))
            if not p.is_dir():
                return None
            return p

        def _from_default() -> Path:
            home = Path.home()
            p = home / '{}-repos'.format(__name__)
            p.mkdir(exist_ok=True)
            return p
        return _from_env() or _from_config() or _from_default()

    @property
    def git_wd(self) -> typing.Optional[Path]:
        return self._git_wd
