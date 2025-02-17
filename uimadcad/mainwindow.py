import warnings
from functools import partial

from madcad.qt import Qt, QWidget, QMainWindow, QDockWidget, QLabel, QApplication
from madcad.rendering import Orthographic
from madcad.mathutils import fvec3, fquat, pi

from . import settings
from .sceneview import SceneView
from .scriptview import ScriptView
from .utils import ToolBar, Button, button, Initializer, action, hlayout, spacer, Menu, Action

class MainWindow(QMainWindow):
	def __init__(self, app):
		self.app = app
		
		Initializer.init(self)
		super().__init__()
		# allows docks to stack horizontally or vertically
		self.setDockNestingEnabled(True)
		
		self.addToolBar(Qt.LeftToolBarArea, ToolBar('file', [
			self.new,
			self.open,
			self.save,
			self.save_as,
			]))
		self.addToolBar(Qt.LeftToolBarArea, ToolBar('execution', [
			self.execute,
			self.clear,
			self.trigger_on_file_change,
			None,
			self.open_uimadcad_settings,
			self.open_pymadcad_settings,
			]))
		self.addToolBar(Qt.LeftToolBarArea, ToolBar('windowing', [
			self.new_sceneview,
			self.new_scriptview,
			# self.copy_layout_to_clipboard,
			None,
			# Button(icon = 'view-dual-symbolic', 
			# 	flat = True,
			# 	description = "reorganize the window following one of the predefined layouts", 
			# 	menu = (Menu('layout', [
					self.layout_default,
					self.layout_double,
					self.layout_triple,
					self.layout_minimal,
				# ]))),
			]))
		
		self.resize(*settings.window['size'])
		self.layout_preset(settings.window['layout'])
	
	def layout_preset(self, name):
		method = getattr(self, 'layout_'+name, None)
		if method:
			method.trigger()
		else:
			warnings.warn('unknown layout preset {}'.format(repr(name)))
			
	def _layout_clear(self):
		for child in self.children():
			if isinstance(child, QDockWidget):
				self.removeDockWidget(child)
	
	@action(shortcut='Ctrl+Shift+J', icon='madcad-layout-default')
	def layout_default(self):
		''' default layout with a script view and a scene view '''
		self._layout_clear()
		
		self.addDockWidget(Qt.TopDockWidgetArea, script := DockedView(ScriptView(self.app), 'script view'))
		self.addDockWidget(Qt.TopDockWidgetArea, main := DockedView(SceneView(self.app), 'main scene view'))
		
		main.widget().orient(fquat(fvec3(+pi/3, 0, -pi/4)))
		
		h = self.width()
		self.resizeDocks(
			[script, main],
			[h//2, h],
			Qt.Horizontal,
			)
	
	@action(shortcut='Ctrl+Shift+K', icon='madcad-layout-double')
	def layout_double(self):
		''' 2 view layout in addition to a script view
			- one main view
			- one orthographic side view
		'''
		self._layout_clear()
		
		self.addDockWidget(Qt.TopDockWidgetArea, script := DockedView(ScriptView(self.app), 'script view'))
		self.addDockWidget(Qt.TopDockWidgetArea, main := DockedView(SceneView(self.app), 'main scene view'))
		self.addDockWidget(Qt.TopDockWidgetArea, second := DockedView(SceneView(self.app, projection = Orthographic()), 'side scene view'))
		
		main.widget().orient(fquat(fvec3(pi/3,0,-pi/4)))
		second.widget().orient(fquat(fvec3(pi/2,0,0)))
		
		# resize docks, Qt is actuelly very bad at computing layouts, so the sizes here will not be acheived by Qt
		# instead empirical values are provided to acheive the desired proportions
		w = self.width()
		self.resize(self.size())
		self.resizeDocks(
			[script, main, second],
			[int(0.1*w), int(1*w), int(0.5*w)],
			Qt.Horizontal,
			)
	
	@action(shortcut='Ctrl+Shift+L', icon='madcad-layout-triple')
	def layout_triple(self):
		''' 3 view layout in addition to a script view
			- one main view
			- two orthographic top and side views
		'''
		self._layout_clear()
		
		self.addDockWidget(Qt.TopDockWidgetArea, script := DockedView(ScriptView(self.app), 'script view'))
		self.addDockWidget(Qt.TopDockWidgetArea, main := DockedView(SceneView(self.app), 'main scene view'))
		self.addDockWidget(Qt.TopDockWidgetArea, top := DockedView(SceneView(self.app, projection = Orthographic()), 'top scene view'))
		self.splitDockWidget(top, side := DockedView(SceneView(self.app, projection = Orthographic()), 'side scene view'), Qt.Vertical)
		
		main.widget().orient(fquat(fvec3(+pi/3, 0, -pi/4)))
		top.widget().orient(fquat(fvec3(0)))
		side.widget().orient(fquat(fvec3(pi/2, 0, -pi/2)))
		
		# resize docks, Qt is actuelly very bad at computing layouts, so the sizes here will not be acheived by Qt
		# instead empirical values are provided to acheive the desired proportions
		w = self.width()
		self.resizeDocks(
			[script, main, top, side],
			[int(0.2*w), int(1*w), int(0.3*w), int(0.3*w)],
			Qt.Horizontal,
			)
		h = self.height()
		self.resizeDocks(
			[top, side],
			[int(h//2), int(1*h)],
			Qt.Vertical,
			)

	@action(shortcut='Ctrl+Shift+M', icon='madcad-layout-minimal')
	def layout_minimal(self):
		''' minimal layout with only one scene view '''
		self._layout_clear()
		
		self.addDockWidget(Qt.TopDockWidgetArea, main := DockedView(SceneView(self.app), 'scene view'))
		
		main.widget().orient(fquat(fvec3(+pi/3, 0, -pi/4)))
	
	@action(icon='madcad-scriptview')
	def new_scriptview(self):
		''' insert a new code view into the window layout '''
		self.addDockWidget(Qt.TopDockWidgetArea, DockedView(ScriptView(self.app), 'script view'))
	
	@action(icon='madcad-sceneview')
	def new_sceneview(self):
		''' insert a new 3d view into the window layout '''
		self.addDockWidget(Qt.TopDockWidgetArea, DockedView(SceneView(self.app), 'scene view'))
		
	def insert_view(self, current:QWidget, new:QWidget):
		''' insert a new DockedView in the mainwindow
		
			- if the current widget is in a DockedView, the new one is inserted to the right or below
			- else it is added at the right of the layout
		'''
		if isinstance(current.parent(), DockedView):
			if current.height() > current.width():
				orientation = Qt.Vertical
			else:
				orientation = Qt.Horizontal
			self.app.window.splitDockWidget(current.parent(), DockedView(new, 'new view'), orientation)
		else:
			self.app.window.addDockWidget(Qt.TopDockWidgetArea, DockedView(new, 'new view'))

	@action(icon='view-dual-symbolic')
	def copy_layout_to_clipboard(self):
		''' dump the layout state to clipboard (for developers) '''
		QApplication.clipboard().setText(str(self.saveState()))
		
	@action(icon='madcad-configure-uimadcad')
	def open_uimadcad_settings(self):
		''' open the settings file of uimadcad '''
		indev
	
	@action(icon='madcad-configure-pymadcad')
	def open_pymadcad_settings(self):
		''' open the settings file of pymadcad '''
		indev
	
	@action(icon='media-seek-forward-symbolic', checked=False, shortcut='Ctrl+Shift+T')
	def trigger_on_file_change(self):
		''' trigger execution on file change
			(save from this editor, or from external editor)
			
			when disabled, you must trigger manually
		'''
		...
	
	@action(icon='media-playback-start', shortcut='Ctrl+Return')
	def execute(self):
		''' run the script. 
			a parcimonial interpreter will take care of reexecuting only the changed code
		'''
		indev
		
	@action(icon='view-refresh', shortcut='Ctrl+Backspace')
	def clear(self):
		''' clear all caches of previous executions 
			next execution will reexecute the whole script from the beginning
		'''
		indev
		
	
	@action(icon='document-new-symbolic', shortcut='Ctrl+N')
	def new(self):
		''' open a new madcad instance with a blank script '''
		indev
	
	@action(icon='document-open-symbolic', shortcut='Ctrl+O')
	def open(self):
		''' close this file and open an other script file '''
		indev
	
	@action(icon='document-save-symbolic', shortcut='Ctrl+S')
	def save(self):
		''' save the current edited file '''
		indev
	
	@action(icon='document-save-as-symbolic', shortcut='Ctrl+Shift+S')
	def save_as(self):
		''' save as a new file '''
		indev

		
class DockedView(QDockWidget):
	def __init__(self, content:QWidget, title:str=None, closable=True, floatable=True):
		super().__init__()
		self.setWidget(content)
		if title:
			self.setWindowTitle(title)
		self.setFeatures(	QDockWidget.DockWidgetMovable
						|	(QDockWidget.DockWidgetFloatable if floatable else 0)
						|	(QDockWidget.DockWidgetClosable if closable else 0)
						)
		self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
		
		if isinstance(getattr(content, 'top', None), QWidget):
			title = QWidget()
			title.setLayout(hlayout([
				content.top,
				spacer(5,0),
				Button(self.setFloating, flat=True, minimal=True,
					icon='window-restore-symbolic', shortcut='Ctrl+Shift+F',
					description="detach view from main window"),
				Button(self.close, flat=True, minimal=True,
					icon='window-close-symbolic', shortcut='Ctrl+Shift+V',
					description="close view"),
				], spacing=0, margins=(0,0,0,0)))
			self.setTitleBarWidget(title)

