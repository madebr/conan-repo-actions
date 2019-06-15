# -*- coding: utf-8 -*-

import typing


class ActionBase(object):
    def __init__(self):
        self.__check = False

    def check(self) -> None:
        self.run_check()
        self.__check = True

    def action(self) -> None:
        if not self.__check:
            self.check()
        self.run_action()

    def description(self) -> str:
        return self.run_description()

    def sub_actions(self) -> typing.Iterable['ActionBase']:
        return self.run_sub_actions()

    def run_check(self):
        raise RuntimeError('This method must be overridden by subclasses')

    def run_action(self):
        raise RuntimeError('This method must be overridden by subclasses')

    def run_description(self) -> str:
        raise RuntimeError('This method must be overridden by subclasses')

    def run_sub_actions(self) -> typing.Iterable['ActionBase']:
        raise RuntimeError('This method must be overridden by subclasses')
