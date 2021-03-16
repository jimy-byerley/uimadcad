#!/usr/bin/python3

from os.path import dirname, realpath
import sys

prefix = dirname(dirname(realpath(sys.argv[0]))) + '/share/madcad'
sys.path.append(prefix)

import launcher
launcher.run(prefix+'/uimadcad')
