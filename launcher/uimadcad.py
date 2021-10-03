from os.path import dirname, realpath
import sys

if sys.platform == 'win32':
	prefix = dirname(realpath(sys.argv[0]))
else:
	prefix = dirname(dirname(realpath(sys.argv[0]))) + '/share/madcad'
sys.path.append(prefix)

try:
	import madcad
except ImportError:
	print("unable to import module madcad, you can install it by typing the following in a terminal:\n\t pip install pymadcad")
	raise
	
try:
	import PyQt5
except ImportError:
	print("unable to import Qt, you can install it by typing the following in a terminal:\n\t pip install PyQt5")
	raise

import launcher
launcher.run(prefix+'/uimadcad')
