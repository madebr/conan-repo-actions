#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path
import yaml
from .fetch_dependencies import ConanReference


def main():
    parser = argparse.ArgumentParser(description='Fetch dependencies of repo')
    parser.add_argument('inputs', type=Path, nargs=argparse.ONE_OR_MORE,
                        help='directories where the dependency information is stored')

    args = parser.parse_args()

    all_packages = {}

    for input in args.inputs:
        indir: Path = input
        for f in indir.iterdir():
            if f.suffix != '.yaml':
                continue
            data = yaml.safe_load(f.open())
            for dependency in data['dependencies']:
                ref = ConanReference.from_refstr(dependency)
                all_packages.setdefault(ref.name, dict()).setdefault(ref.version, []).append(f.stem)

    s = yaml.safe_dump(all_packages)
    print(s)


if __name__ == '__main__':
    main()
