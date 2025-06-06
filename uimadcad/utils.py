import sys
import traceback
import locale
import signal
from threading import Thread, Lock
from functools import partial
from collections import deque
from types import MethodType
from time import perf_counter

from madcad.qt import (
	Qt, QTimer, Signal, QSize, QMargins, QStyle,
	QIcon, QKeySequence, QColor, QTextCharFormat, QTextCursor,
	QWidget, QBoxLayout, QLayoutItem, QVBoxLayout, QHBoxLayout, QSizePolicy, QSplitter,
	QPushButton, QDockWidget, QToolBar, QActionGroup, QButtonGroup,
	QMenuBar, QMenu, 
	QPlainTextEdit, QTextEdit,
	QApplication, QAction, QShortcut, QPalette,
	)
from madcad.mathutils import uvec2, vec2, vec4, ivec4, vec3, fvec3, mix, clamp

from .icon import icon_from_theme

__all__ = [
	'singleton', 'catchtime', 'qtmain', 'qtschedule', 'qtinvoke', 'qtquit',
	'Initializer',
	'ToolBar', 'MenuBar', 'Menu', 'Action', 'Shortcut',
	'Button', 'action', 'button', 'group', 'shortcut',
	'PlainTextEdit',
	'boxlayout', 'vlayout', 'hlayout', 'dock', 'window', 'spacer', 'signal',
	]


qtstopped = False

# setup that Ctrl+C will stop the python interpreter and the Qt application
def signal_interrupt(signal, frame):
	global qtstopped
	# immediately exit the program
	#import os
	#os._exit(1)
	
	# raise in the current thread
	if QApplication.instance() and not qtstopped:	
		qtstopped = True
		print(' quit Qt')
		qtquit()
	else:
		raise KeyboardInterrupt

signal.signal(signal.SIGINT, signal_interrupt)


class singleton(object):
	''' function decorator that caches the result and never reexecute a second time'''
	__slots__ = 'func', 'executed', 'value'
	def __init__(self, func):
		self.func = func
		self.executed = False
		
	def __call__(self):
		if not self.executed:
			self.value = self.func()
			self.executed = True
		return self.value

class catchtime(object):
	''' simple object that counts elapsed time using a specific chrono '''
	__slots__ = 'time', 'total', 'start'
	
	def __init__(self, time=perf_counter):
		self.time = time
		self.total = 0
		self.start = None
		
	def reset(self):
		self.total = 0
		if self.start is not None:
			self.start = self.time()
	
	def __enter__(self):
		''' start chronometer, it does not reset the already recorded time '''
		self.start = self.time()
		return self

	def __exit__(self, type, value, traceback):
		''' stop chronometer '''
		self.total += self.time()-self.start
		self.start = None

	def __call__(self):
		''' return the recorded time '''
		if self.start is None:	elapsed = 0
		else:					elapsed = self.time()-self.start
		return elapsed + self.total

	def __repr__(self):
		''' returned time '''
		return '<chrono {}>'.format(self())


qttasks = deque()
qttasks_timer = None
def qtmain(app=None):
	''' create and run the QApplication and the Qt main loop '''
	global qttasks_timer, qtstopped
	
	if not app:	
		app = QApplication(sys.argv)
	
	locale.setlocale(locale.LC_ALL, 'C')
	
	def process_tasks():
		while qttasks:
			qttasks.popleft() ()
			
	qttasks_timer = QTimer()
	qttasks_timer.setInterval(50)
	qttasks_timer.timeout.connect(process_tasks)
	qttasks_timer.start()
	
	qtstopped = False
	app.exec()

def qtschedule(callback):
	''' put a task for the Qt thread to execute as soon as possible '''
	qttasks.append(callback)

def qtinvoke(callback):
	''' same as qtschedule but wait for the task end '''
	lock = Lock()
	lock.acquire()
	result = [None, None]
	def wrapper():
		try:	result[0] = callback()
		except Exception as err:
			print_exc()
			result[1] = err
		lock.release()
	qtschedule(wrapper)
	lock.acquire()
	if result[1]:	raise result[1]
	return result[0]
	
def qtquit():
	''' close the QApplication it it exists '''
	app = QApplication.instance()
	if app:
		app.quit()



class MenuBar(QMenuBar):
	def __init__(self, menus:list=(), parent=None):
		super().__init__(parent)
		for name, menu in menus:
			self.addMenu(Menu(name, menu))

class Menu(QMenu):
	def __init__(self, name:str, actions:list=(), parent=None):
		super().__init__(name, parent)
		for action in actions:
			if action is None:
				self.addSeparator()
			elif isinstance(action, QMenu):
				self.addMenu(action)
			elif isinstance(action, QAction):
				self.addAction(action)

class ToolBar(QToolBar):
	def __init__(self, name:str, 
			widgets:list=(), 
			orientation=Qt.Horizontal, 
			margins:QMargins=None, 
			icon_size:QSize|str=None,
			parent=None):
		super().__init__(name, parent)
		self.setOrientation(orientation)
		for widget in widgets:
			if widget is None:
				self.addSeparator()
			elif isinstance(widget, Action):
				self.addAction(widget)
			else:
				self.addWidget(widget)
		if icon_size:
			if isinstance(icon_size, str):
				match icon_size:
					case 'small':  metric = QStyle.PM_SmallIconSize
					case 'normal': metric = QStyle.PM_ToolBarIconSize
					case 'large':  metric = QStyle.PM_LargeIconSize
					case _:   raise ValueError('bad size {}'.format(repr(icon_size)))
				size = QApplication.instance().style().pixelMetric(metric)
				size = QSize(size, size)
			self.setIconSize(size)
		if margins:
			self.layout().setContentsMargins(margins)
				
def group(actions, parent=None):
	if isinstance(actions[0], Action):	
		group = QActionGroup(parent)
		for action in actions:
			group.addAction(action)
	elif isinstance(actions[1], Button):
		group = QButtonGroup(parent)
		for action in actions:
			group.addButton(action)
				
class Action(QAction):
	def __init__(self, 
			callback:callable=None, 
			name:str=None, 
			icon:str|QIcon=None, 
			shortcut:str|QKeySequence=None, 
			description:str=None, 
			checked:bool=None,
			checkable:bool=False,
			group=None,
			priority=QAction.NormalPriority,
			context=Qt.WindowShortcut,
			parent=None):
		super().__init__(parent)
		if callback:
			if checked is None:
				self.triggered.connect(callback)
			else:
				self.toggled.connect(callback)
			if name is None:
				name = callback.__name__.replace('_', ' ')
			if description is None: 
				description = callback.__doc__
		if icon:    
			if isinstance(icon, str):
				icon = icon_from_theme(icon)
			self.setIcon(icon)
		if shortcut:
			if isinstance(shortcut, str):
				key = shortcut
				shortcut = QKeySequence(shortcut)
			elif isinstance(shortcut, QKeySequence):
				key = shortcut.key().toString()
			self.setShortcut(shortcut)
			if description:
				description += '\n\n(shortcut: {})'.format(key)
		if checked is not None:
			checkable = True
			self.setChecked(checked)
		if name:  
			self.setText(name)
			self.setIconText(name)
		if description is not None: 
			description = dedent(description)
			self.setToolTip(description)
			self.setWhatsThis(description)
		self.setCheckable(checkable)
		self.setPriority(priority)
		self.setShortcutContext(context)
		if group:
			group.addAction(self)
			
class Button(QPushButton):
	def __init__(self, 
			callback:callable=None, 
			name:str=None, 
			icon:str|QIcon=None, 
			shortcut:str|QKeySequence=None, 
			description:str=None, 
			checked:bool=None,
			checkable:bool=False,
			flat:bool=False,
			menu:QMenu=None,
			minimal:bool=False,
			group=None,
			parent=None):
		super().__init__(parent)
		if callback:
			if checked is None:
				self.clicked.connect(callback)
			else:
				self.toggled.connect(callback)
			if name is None and icon is None:    
				name = callback.__name__.replace('_', ' ')
			if description is None: 
				description = callback.__doc__
		if icon:    
			if isinstance(icon, str):
				icon = icon_from_theme(icon)
			self.setIcon(icon)
		if shortcut:
			if isinstance(shortcut, str):
				key = shortcut
				shortcut = QKeySequence(shortcut)
			elif isinstance(shortcut, QKeySequence):
				key = shortcut.key().toString()
			self.setShortcut(shortcut)
			if description:
				description += '\n\n(shortcut: {})'.format(key)
		if checked is not None:
			checkable = True
			self.setChecked(checked)
		if name:
			self.setText(name)
		if description is not None: 
			description = dedent(description)
			self.setToolTip(description)
			self.setWhatsThis(description)
		if menu:
			self.setMenu(menu)
		if minimal:
			self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
		else:
			self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		self.setFlat(flat)
		self.setCheckable(checkable)
		self.setFocusPolicy(Qt.NoFocus)
		if group:
			group.addAction(self)
			
class Shortcut(QShortcut):
	def __init__(self, callback:callable, shortcut:str, context=Qt.WindowShortcut, parent=None):
		super().__init__(shortcut, parent, callback)

def propertywrite(func):
	''' decorator to create a property with only a write function '''
	fieldname = '_'+func.__name__
	def getter(self):	return getattr(self, fieldname)
	def setter(self, value):
		setattr(self, fieldname, value)
		func(self, value)
	return property(getter, setter)

class Initializer:
	def decorator(cls):
		def parametrizer(**kwargs):
			def decorator(callback):
				def init(self, **kwargs2):
					bound = partial(callback, self)
					bound.__name__ = callback.__name__
					bound.__doc__ = callback.__doc__
					return cls(bound, **kwargs, **kwargs2)
				return Initializer(init)
			return decorator
		return parametrizer
	
	def __init__(self, init):
		self.init = init
	
	def process(obj, **kwargs):
		for name, initializer in vars(type(obj)).items():
			if isinstance(initializer, Initializer):
				setattr(obj, name, initializer.init(obj, **kwargs))

action = Initializer.decorator(Action)
button = Initializer.decorator(Button)
shortcut = Initializer.decorator(Shortcut)


class PlainTextEdit(QPlainTextEdit):
	''' text view to specify objects main.currentenv we want to append to main.scene '''
	def __init__(self, interaction: Qt.TextInteractionFlags = None, parent=None):
		super().__init__(parent)
		self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
		if interaction:
			self.setTextInteractionFlags(interaction)
		
	def sizeHint(self):
		return QSize(20, self.document().lineCount())*self.document().defaultFont().pointSize()

class Splitter(QSplitter):
	def __init__(self, children:list=(), orientation=Qt.Horizontal, parent=None):
		super().__init__(orientation, parent)
		for child in children:
			self.addWidget(child)
		
def boxlayout(items: list, orientation=QBoxLayout.TopToBottom, spacing=None, margins=None) -> QBoxLayout:
	layout = QBoxLayout(orientation)
	if spacing is not None:
		layout.setSpacing(spacing)
	if margins is not None:
		if isinstance(margins, int):
			layout.setContentsMargins(margins, margins, margins, margins)
		elif isinstance(margins, tuple):
			layout.setContentsMargins(*margins)
		else:
			layout.setContentsMargins(margins)
	for item in items:
		if isinstance(item, QLayoutItem):
			layout.addItem(item)
		elif isinstance(item, QWidget):
			layout.addWidget(item)
	return layout
	
def vlayout(items: list, **kwargs) -> QVBoxLayout:
	return boxlayout(items, orientation=QBoxLayout.TopToBottom, **kwargs)
	
def hlayout(items: list, **kwargs) -> QHBoxLayout:
	return boxlayout(items, orientation=QBoxLayout.LeftToRight, **kwargs)
	
def widget(layout, parent=None) -> QWidget:
	widget = QWidget(parent)
	widget.setLayout(layout)
	return widget

def dock(widget, title, closable=True, floatable=True):
	''' create a QDockWidget '''
	dock = QDockWidget(title)
	dock.setWidget(widget)
	dock.setFeatures(	QDockWidget.DockWidgetMovable
					|	(QDockWidget.DockWidgetFloatable if floatable else 0)
					|	(QDockWidget.DockWidgetClosable if closable else 0)
					)
	dock.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
	return dock
	
def window(widget: QWidget) -> QWidget:
	widget.setParent(None)
	widget.show()
	return widget

def spacer(w: int, h: int) -> QWidget:
	space = QWidget()
	space.setMinimumSize(w, h)
	return space

signal = Signal

def charformat(background=None, foreground=None, italic=None, overline=None, strikeout=None, weight=None, font=None) -> QTextCharFormat:
	''' create a QTextCharFormat '''
	fmt = QTextCharFormat()
	if background:	fmt.setBackground(background)
	if foreground:	fmt.setForeground(foreground)
	if italic is not None:		fmt.setFontItalic(italic)
	if overline is not None:	fmt.setFontOverline(overline)
	if strikeout is not None:	fmt.setFontStrikeOut(strikeout)
	if weight:					fmt.setFontWeight(weight)
	if font:	fmt.setFont(font)
	return fmt

def extraselection(cursor: QTextCursor, format: QTextCharFormat) -> QTextEdit.ExtraSelection:
	''' create an ExtraSelection '''
	o = QTextEdit.ExtraSelection()
	o.cursor = cursor
	o.format = format
	return o
	

def palette_simple(
	base:vec3=vec3(0), text:vec3=vec3(1), highlight:vec3=vec3(0.1, 0.2, 1), 
	link:vec3=None, view:vec3=None, input:vec3=None, button:vec3=None,
	):
	if not link: link = mix(base, highlight, 0.7)
	if not view: view = clamp(mix(base, text, -0.05), 0, 1)
	if not input: input = mix(base, text, 1.1)
	if not button: button = mix(base, text, 0.02)
	
	palette = QPalette()
	
	palette.setColor(QPalette.Window, vec_to_qcolor(base))
	palette.setColor(QPalette.Base, vec_to_qcolor(view))
	palette.setColor(QPalette.AlternateBase, vec_to_qcolor(mix(base, text, 0.3)))
	palette.setColor(QPalette.WindowText, vec_to_qcolor(mix(base, text, 0.9)))
	
	palette.setColor(QPalette.Light, vec_to_qcolor(mix(base, text, 0.1)))
	palette.setColor(QPalette.Midlight, vec_to_qcolor(mix(base, text, 0.25)))
	palette.setColor(QPalette.Mid, vec_to_qcolor(mix(base, text, 0.5)))
	palette.setColor(QPalette.Dark, vec_to_qcolor(mix(base, text, 0.7)))
	palette.setColor(QPalette.Shadow, vec_to_qcolor(mix(base, text, 0.8)))
	
	palette.setColor(QPalette.Text, vec_to_qcolor(input))
	palette.setColor(QPalette.BrightText, vec_to_qcolor(mix(text, link, 0.5)))
	
	palette.setColor(QPalette.Highlight, vec_to_qcolor(highlight))
	palette.setColor(QPalette.Link, vec_to_qcolor(link))
	palette.setColor(QPalette.LinkVisited, vec_to_qcolor(link*0.6))
	
	palette.setColor(QPalette.Button, vec_to_qcolor(button))
	palette.setColor(QPalette.ButtonText, vec_to_qcolor(text))
	
	palette.setColor(QPalette.PlaceholderText, vec_to_qcolor(mix(base, text, 0.5)))
	
	palette.setColor(QPalette.ToolTipBase, vec_to_qcolor(base))
	palette.setColor(QPalette.ToolTipText, vec_to_qcolor(text))
	
	disabled = 0.5
	palette.setColor(QPalette.Disabled, QPalette.Text, vec_to_qcolor(mix(base, input, disabled)))
	palette.setColor(QPalette.Disabled, QPalette.BrightText, vec_to_qcolor(mix(base, mix(text, link, 0.5), disabled)))
	palette.setColor(QPalette.Disabled, QPalette.Highlight, vec_to_qcolor(mix(base, highlight, disabled)))
	palette.setColor(QPalette.Disabled, QPalette.Link, vec_to_qcolor(mix(base, link, disabled)))
	palette.setColor(QPalette.Disabled, QPalette.LinkVisited, vec_to_qcolor(mix(base, link*0.6, disabled)))
	palette.setColor(QPalette.Disabled, QPalette.ButtonText, vec_to_qcolor(mix(base, text, disabled)))
	palette.setColor(QPalette.Disabled, QPalette.PlaceholderText, vec_to_qcolor(mix(base, text, 0.5*disabled)))
	
	return palette

def mix_qcolor(a: QColor, b: QColor, x: float) -> QColor:
	a = a.toRgb()
	b = b.toRgb()
	y = 1-x
	return QColor(
		int(a.red()*y + b.red()*x),
		int(a.green()*y + b.green()*x),
		int(a.blue()*y + b.blue()*x),
		int(a.alpha()*y + b.alpha()*x),
		)

def qcolor_to_vec(color: QColor) -> vec4:
	color = color.toRgb()
	return vec4(color.red(), color.green(), color.blue(), color.alpha()) / 255
	
def vec_to_qcolor(color: vec4) -> QColor:
	if isinstance(color, fvec3):
		color = vec3(color)
	if isinstance(color, vec3):
		color = vec4(color,1)
	color = ivec4(color * 255)
	return QColor(color.x, color.y, color.z, color.w)
	
def qsize_to_vec(size: QSize) -> uvec2:
	return vec2(size.width(), size.height())
	
def vec_to_qsize(size: uvec2) -> QSize:
	return QSize(*uvec2(size))

def dedent(text):
	text = text.strip()
	indent = None
	it = iter(text)
	for char in it:
		if char == '\n': 
			indent = char
			break
	for char in it:
		if char == '\n':	
			indent = char
		elif char.isspace():  
			indent += char
		else:  
			break
	if indent:
		return text.replace(indent, '\n')
	else:
		return text
