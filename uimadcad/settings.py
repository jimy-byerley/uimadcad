import os, yaml
from os.path import dirname, exists
from madcad.mathutils import *	
import madcad
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QStyleFactory
from PyQt5.QtGui import QPalette

from .common import ressourcedir


execution = {
	'onstartup': True,			# execution at program startup
	'trigger': 1,				# execution trigger: {0: manual, 1: on line change, 2: on typing}
	'steptime': 0.1,			# execution time tolerated between backups, if a block runs a longer time, the interpreter will start create a backup
	'checkdanger': 'startup',	# when to check for dangerous code ('never'/False, 'startup'/True, 'always')
	}
	
view = {
	'layout': 'default',
	'enable_floating': False,	# floating dockable windows, may have performance issues with big meshes
	'window_size': [900,500],
	'quick_toolbars': True,		# display the quickaccess toolbars
	'color_preset': 'system',
	'stylesheet': 'breeze-artificial',
	}

scriptview = {
	'linewrap': False,
	'linenumbers': False,
	'autoterminator': True,
	'autocomplete': True,
	
	'tabsize': 4,
	'font': ['NotoMono', 8],
	'system_theme': True,
	
	'background': fvec3(0,0,0),
	'highlight_background': fvec4(40/255, 200/255, 240/255, 60/255),
	'edition_background': fvec4(255/255, 200/255, 50/255, 60/255),
	'selected_background': fvec4(0.3, 0.6, 0.15, 0.2),
	'normal_color': fvec3(1, 1, 1),
	'keyword_color': fvec3(50/255, 210/255, 150/255),
	'operator_color': fvec3(50/255, 100/255, 150/255),
	'call_color': fvec3(150/255, 255/255, 120/255),
	'number_color': fvec3(50/255, 100/255, 255/255),
	'string_color': fvec3(100/255, 200/255, 255/255),
	'comment_color': fvec3(0.5, 0.5, 0.5),
	}

configdir = madcad.settings.configdir
locations = {
	'config': configdir+'/madcad',
	'uisettings': configdir+'/madcad/uimadcad.yaml',
	'pysettings': configdir+'/madcad/pymadcad.yaml',
	'colors_presets': configdir+'/madcad/color-presets.yaml',
	'startup': configdir+'/madcad/startup.py',
	}

settings = {'execution':execution, 'view':view, 'scriptview':scriptview}


def qtc(c):
	''' convert a QColor or QPalette role to fvec3'''
	return fvec3(c.red(), c.green(), c.blue()) / 255
	
def ctq(c):
	''' convert a fvec3 to QColor '''
	return QColor(*ivec3(255*c))

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
	os.remove(locations['uisettings'])

def load(file=None):
	''' load the settings directly in this module, from the specified file or the default one '''
	if not file:	file = locations['uisettings']
	if isinstance(file, str):	file = open(file, 'r')
	changes = yaml.safe_load(file)
	def update(dst, src):
		for key in dst:
			if key in src:
				if isinstance(dst[key], dict) and isinstance(src[key], dict):	
					update(dst[key], src[key])
				elif isinstance(dst[key], fvec3):	dst[key] = fvec3(src[key])
				elif isinstance(dst[key], fvec4):	dst[key] = fvec4(src[key])
				else:
					dst[key] = src[key]
	update(settings, changes)


def dump(file=None):
	''' load the current settings into the specified file or to the default one '''
	if not file:	file = locations['uisettings']
	if isinstance(file, str):	file = open(file, 'w')
	yaml.add_representer(fvec3, lambda dumper, data: dumper.represent_list(round(f,3) for f in data))
	yaml.add_representer(fvec4, lambda dumper, data: dumper.represent_list(round(f,3) for f in data))
	file.write(yaml.dump(settings, default_flow_style=None, width=60, indent=4))
	

def use_qt_colors():
	''' set the color settings to fit the current system colors '''
	from PyQt5.QtWidgets import QApplication
	palette = QApplication.instance().palette()
	def qtc(role):
		''' convert a QColor or QPalette role to fvec3'''
		c = palette.color(role)
		return fvec3(c.red(), c.green(), c.blue()) / 255
		
	background = clamp(mix(qtc(palette.Base), fvec3(0.5), -0.1), fvec3(0), fvec3(1))
	normal = clamp(mix(qtc(palette.Text), fvec3(0.5), -0.1), fvec3(0), fvec3(1))
	darken = 0.9 + 0.1*(norminf(normal)-norminf(background))
	
	second = qtc(palette.Highlight) +1e-3
	second = clamp(second / norminf(second) * darken, fvec3(0), fvec3(1)) **2
	accent = mix(second, fvec3(1, 1, 0)*norminf(second), 0.65)
	accent = clamp(accent, fvec3(0), fvec3(1))
	
	rare = mix(accent, second, 0.3)
	
	scriptview.update({
		'background': background,
		'highlight_background': fvec4(second, 0.2),
		'edition_background': fvec4(rare, 0.2),
		'selected_background': fvec4(accent, 0.2),
		'normal_color': normal,
		'keyword_color': rare,
		'operator_color': normal,
		'call_color': mix(accent, normal, 0.3),
		'number_color': second,
		'string_color': second,
		'comment_color': mix(normal, background, 0.6),
		})
	
def list_color_presets(name=None):
	names = ['system']
	for name in os.listdir(ressourcedir +'/themes'):
		radix, ext = os.path.splitext(name)
		if ext == '.yaml':
			names.append(radix)
	return names

def use_color_preset(name=None):	
	if not name:	
		name = view['color_preset']
	
	palette = QPalette()
	if name != 'system':
		
		file = ressourcedir +'/themes/'+ name + '.yaml'
		try:
			colors = yaml.safe_load(open(file, 'r'))
		except FileNotFoundError as err:
			print(err)
			return
		for key, value in colors.items():
			colors[key] = fvec3(value)
		
		# complete the minimal color set
		if 'background' not in colors:		colors['background'] = colors['Window']
		if 'base' not in colors:			colors['base'] = colors['Base']
		if 'text' not in colors:			colors['text'] = colors['Text']
		if 'decoration' not in colors:		colors['decoration'] = colors['Dark']
		if 'colored' not in colors:			colors['colored'] = colors['highlight']
		
		# complete the palette colors with the colors of the minimal set
		if 'Window' not in colors:			colors['Window'] = colors['background']
		if 'WindowText' not in colors:		colors['WindowText'] = mix(colors['background'], colors['decoration'], 0.8)
		if 'Base' not in colors:			colors['Base'] = colors['base']
		if 'AlternateBase' not in colors:	colors['AlternateBase'] = mix(colors['base'], colors['decoration'], 0.05)
		if 'Highlight' not in colors:		colors['Highlight'] = colors['colored']
		if 'Light' not in colors:			colors['Light'] = mix(colors['background'], colors['decoration'], 0.08)
		if 'Midlight' not in colors:		colors['Midlight'] = mix(colors['background'], colors['decoration'], 0.2)
		if 'Dark' not in colors:			colors['Dark'] = mix(colors['background'], colors['decoration'], 0.3)
		if 'Mid' not in colors:				colors['Mid'] = mix(colors['background'], colors['decoration'], 0.5)
		if 'Shadow' not in colors:			colors['Shadow'] = mix(colors['background'], colors['decoration'], 0.8)
		
		if 'Text' not in colors:			colors['Text'] = colors['text']
		if 'BrightText' not in colors:		colors['BrightText'] = mix(colors['colored'], colors['text'], 0.5)
		if 'HighlightedText' not in colors:	colors['HighlightedText'] = mix(colors['background'], colors['colored'], 0.05)
		
		if 'Button' not in colors:			colors['Button'] = mix(colors['background'], colors['decoration'], 0.7)
		if 'ButtonText' not in colors:		colors['ButtonText'] = mix(colors['background'], colors['decoration'], 0.8)
		
		if 'Link' not in colors:			colors['Link'] = colors['colored']
		if 'LinkVisited' not in colors:		colors['LinkVisited'] = mix(colors['background'], colors['colored'], 0.7)
		
		if 'PlaceholderText' not in colors:	colors['PlaceholderText'] = mix(colors['background'], colors['text'], 0.4)
		if 'ToolTipBase' not in colors:		colors['ToolTipBase'] = colors['background']
		if 'ToolTipText' not in colors:		colors['ToolTipText'] = colors['decoration']
		
		# update the system palette with the theme colors
		for name, value in colors.items():
			if hasattr(QPalette, name) and isinstance(getattr(QPalette, name), int):
				palette.setColor(getattr(QPalette, name), ctq(value))
	
	app = QApplication.instance()
	app.setPalette(palette)
	app.setStyleSheet(app.styleSheet())


def list_stylesheets(name=None):
	names = [key.lower()  for key in QStyleFactory.keys()]
	for name in os.listdir(ressourcedir +'/themes'):
		radix, ext = os.path.splitext(name)
		if ext == '.qss':
			names.append(radix)
	return names

def use_stylesheet(name=None):
	if not name:
		name = view['stylesheet']
	
	app = QApplication.instance()
	keys = set(key.lower()  for key in QStyleFactory.keys())
	if name in keys:
		app.setStyle(name)
		app.setStyleSheet('')
	else:
		try:
			app.setStyleSheet(open(ressourcedir+'/themes/'+name+'.qss', 'r').read())
			app.setStyle('fusion')
		except FileNotFoundError as err:
			print(err)
			return

