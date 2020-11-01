import os, json
from os.path import dirname, exists

execution = {
	'onstartup': False,
	'trigger': 1,
	'steptime': 0.1,
	'checkdanger': 'startup',	# 'never'/False, 'startup'/True, 'always'
	}
	
view = {
	'layout': 'default',
	'theme': 'system',
	'enable_floating': False,	# floating dockable windows, may have performance issues with big meshes
	'window-size': (640,480),
	}

scriptview = {
	'tabsize': 4,
	'linewrap': False,
	'linenumbers': False,
	'font': ('NotoMono', 7),
	}

highlighter = {
	'background': (0,0,0),
	'currentline': (0.5, 0.5, 0.5),
	'editing': (20/255, 80/255, 0),
	'normal': (1, 1, 1),
	'keyword': None,
	'operator': None,
	'call': None,
	'number': None,
	'string': None,
	'comment': None,
	}

home = os.getenv('HOME')
locations = {
	'config': home+'/.config/madcad',
	'uisettings': home+'/.config/madcad/uimadcad.json',
	'pysettings': home+'/.config/madcad/pymadcad.json',
	'startup': home+'/.config/madcad/startup.py',
	}


settings = {'execution':execution, 'view':view, 'scriptview':scriptview, 'highlighter':highlighter}


def install():
	''' create and fill the config directory if not already existing '''
	file = locations['uisettings']
	if not exists(file):
		os.makedirs(dirname(file), exist_ok=True)
		dump()
	file = locations['startup']
	if not exists(file):
		os.makedirs(dirname(file), exist_ok=True)
		open(file, 'w').write('from madcad import *\n\n')
		
def clean():
	''' delete the default configuration file '''
	os.rmdir(locations['config'])

def load(file=None):
	''' load the settings directly in this module, from the specified file or the default one '''
	if not file:	file = locations['uisettings']
	if isinstance(file, str):	file = open(file, 'r')
	changes = json.load(file)
	for group in settings:
		if group in changes:
			settings[group].update(changes[group])

def dump(file=None):
	''' load the current settings into the specified file or to the default one '''
	if not file:	file = locations['uisettings']
	if isinstance(file, str):	file = open(file, 'w')
	json.dump(settings, file, indent='\t', ensure_ascii=True)
	

