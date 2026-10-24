#!/usr/bin/env python3
"""Run portable checks without Gradle, the Cisco SDK, credentials or a PT instance."""
import argparse
import os
from pathlib import Path
import py_compile
import re
import shutil
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--require-java',action='store_true',help='Require JDK 21+ and fail if any test is skipped')
    mode.add_argument('--python-only',action='store_true',help='Explicitly skip Java harnesses to test offline Python independence')
    args=parser.parse_args(argv)
    if args.python_only:
        os.environ['PT_MCP_PYTHON_ONLY']='1'
    elif args.require_java:
        os.environ.pop('PT_MCP_PYTHON_ONLY',None)
        if not shutil.which('javac') or not shutil.which('java'):
            parser.error('--require-java needs javac and java on PATH')
        result=subprocess.run(['javac','-version'],text=True,capture_output=True,timeout=10)
        version=re.search(r'javac\s+(\d+)',result.stdout+result.stderr)
        if result.returncode or not version or int(version.group(1))<21:
            parser.error('--require-java needs JDK 21 or newer')
    sys.path.insert(0,str(ROOT))
    for directory in (ROOT,ROOT/'scripts',ROOT/'tests'):
        for source in directory.glob('*.py'):
            py_compile.compile(str(source),doraise=True)
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if args.require_java and result.skipped:
        print('Required CI mode does not permit skipped tests.',file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
