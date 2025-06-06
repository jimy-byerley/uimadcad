import os, yaml
from os.path import dirname, exists
from madcad.mathutils import *	
import madcad
from madcad.qt import (
	QColor,
	QApplication, QStyleFactory,
	QPalette,
	)

from . import resourcedir
from .utils import palette_simple


window = {
	'size': [900,500],
	'layout': 'default',
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

settings = {'window':window, 'scriptview':scriptview}


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
	from madcad.qt import QApplication
	palette = QApplication.instance().palette()
	def qtc(role):
		''' convert a QColor or QPalette role to fvec3'''
		c = palette.color(role)
		return fvec3(c.red(), c.green(), c.blue()) / 255
		
	background = clamp(mix(qtc(QPalette.Base), fvec3(0.5), -0.1), fvec3(0), fvec3(1))
	normal = clamp(mix(qtc(QPalette.Text), fvec3(0.5), -0.1), fvec3(0), fvec3(1))
	darken = 0.9 + 0.1*(norminf(normal)-norminf(background))
	
	second = qtc(QPalette.Highlight) +1e-3
	second = clamp(second / norminf(second) * darken, fvec3(0), fvec3(1)) **2
	accent = mix(second, fvec3(1, 1, 0)*norminf(second), 0.65)
	accent = clamp(accent, fvec3(0), fvec3(1))
	
	rare = mix(accent, second, 0.3)
	
	selection = mix(fvec3(0.4, 1, 0), qtc(QPalette.Highlight), 0.6)
	selection *= mix(1/max(selection), max(normal), 0.3)
	hover = mix(fvec3(0., 0.4, 1), qtc(QPalette.Highlight), 0.3)
	hover *= mix(1/max(selection), max(normal), 0.3)
	
	scriptview.update({
		'background': background,
		'hover_background': fvec4(hover, 0.3),
		'selection_background': fvec4(selection, 0.2),
		'edition_background': fvec4(rare, 0.2),
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
	for name in os.listdir(resourcedir +'/themes'):
		radix, ext = os.path.splitext(name)
		if ext == '.yaml':
			names.append(radix)
	return names

def use_color_preset(name=None):	
	if not name:	
		name = window['color_preset']
	
	palette = QPalette()
	
	if name == 'system':
		palette = palette_simple(
			base = qtc(palette.color(QPalette.Window)),
			text = qtc(palette.color(QPalette.WindowText)),
			highlight = qtc(palette.color(QPalette.Highlight)),
			link = qtc(palette.color(QPalette.Link)),
			input = qtc(palette.color(QPalette.Text)),
			)
	else:
		file = resourcedir +'/themes/'+ name + '.yaml'
		try:
			palette = palette_simple(**{ k:vec3(v)  for k,v in yaml.safe_load(open(file, 'r')).items() })
		except (FileNotFoundError, TypeError) as err:
			print(err)
			return
	
	app = QApplication.instance()
	app.setPalette(palette)
	app.setStyleSheet(app.styleSheet())


def list_stylesheets(name=None):
	names = [key.lower()  for key in QStyleFactory.keys()]
	for name in os.listdir(resourcedir +'/themes'):
		radix, ext = os.path.splitext(name)
		if ext == '.qss':
			names.append(radix)
	return names

def use_stylesheet(name=None):
	if not name:
		name = window['stylesheet']
	
	app = QApplication.instance()
	keys = set(key.lower()  for key in QStyleFactory.keys())
	if name in keys:
		app.setStyle(name)
		app.setStyleSheet('')
	else:
		try:
			app.setStyleSheet(open(resourcedir+'/themes/'+name+'.qss', 'r').read())
			app.setStyle('fusion')
		except FileNotFoundError as err:
			print(err)
			return

