import warnings
import sys
import os
from functools import partial

from madcad.qt import Qt, QWidget, QMainWindow, QDockWidget, QLabel, QApplication, QShortcutEvent, QEvent
from madcad.rendering import Orthographic
from madcad.mathutils import fvec3, fquat, pi

from . import settings
from .sceneview import SceneView
from .scriptview import ScriptView
from .utils import ToolBar, Button, button, Initializer, action, hlayout, spacer, Menu, Action, shortcut

class MainWindow(QMainWindow):
	def __init__(self, app):
		self.app = app
		
		super().__init__()
		Initializer.process(self, parent=self)
		# get the '*' marker in the window title when the document has been modified since last save
		self.app.document.modificationChanged.connect(self.setWindowModified)
		# allows docks to stack horizontally or vertically
		self.setDockNestingEnabled(True)
		
		self.addToolBar(Qt.LeftToolBarArea, ToolBar('file', [
			self.app.save,
			self.app.save_as,
			self.app.open,
			self.app.new,
			]))
		self.addToolBar(Qt.LeftToolBarArea, ToolBar('execution', [
			self.app.execute,
			self.app.clear,
			self.app.trigger_on_file_change,
			None,
			self.app.open_uimadcad_settings,
			self.app.open_pymadcad_settings,
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
	
	def layout_preset(self, name:str):
		''' apply the given layout preset, it must match an action of the same name in this class '''
		method = getattr(self, 'layout_'+name, None)
		if method:
			method.trigger()
		else:
			warnings.warn('unknown layout preset {}'.format(repr(name)))
			
	def _layout_clear(self):
		''' remove all docked widgets from the window '''
		for child in self.children():
			if isinstance(child, DockedView):
				self.removeDockWidget(child)
	
	@shortcut(shortcut='Esc')
	def focus_other(self):
		''' switch focus between active sceneview and active scriptview  '''
		active = self.app.active
		if active.sceneview and not active.sceneview.hasFocus():
			active.sceneview.setFocus()
		elif active.scriptview and not active.scriptview.hasFocus():
			active.scriptview.setFocus()
			active.scriptview.editor.ensureCursorVisible()
			
	@action(shortcut='Ctrl+Shift+J', icon='madcad-layout-default')
	def layout_default(self):
		''' default layout with a script view and a scene view '''
		self._layout_clear()
		
		self.addDockWidget(Qt.TopDockWidgetArea, main := DockedView(SceneView(self.app), 'main scene view'))
		self.addDockWidget(Qt.TopDockWidgetArea, script := DockedView(ScriptView(self.app), 'script view'))
		
		main.widget().orient(fquat(fvec3(+pi/3, 0, -pi/4)))
		
		w = self.width()
		self.resizeDocks(
			[main, script],
			[w, int(0.7*w)],
			Qt.Horizontal,
			)
		
		main.widget().setFocus()
	
	@action(shortcut='Ctrl+Shift+K', icon='madcad-layout-double')
	def layout_double(self):
		''' 2 view layout in addition to a script view
			- one main view
			- one orthographic side view
		'''
		self._layout_clear()
		
		self.addDockWidget(Qt.TopDockWidgetArea, second := DockedView(SceneView(self.app, projection = Orthographic()), 'side scene view'))
		self.addDockWidget(Qt.TopDockWidgetArea, main := DockedView(SceneView(self.app), 'main scene view'))
		self.addDockWidget(Qt.TopDockWidgetArea, script := DockedView(ScriptView(self.app), 'script view'))
		
		main.widget().orient(fquat(fvec3(pi/3,0,-pi/4)))
		second.widget().orient(fquat(fvec3(pi/2,0,0)))
		
		# resize docks, Qt is actuelly very bad at computing layouts, so the sizes here will not be acheived by Qt
		# instead empirical values are provided to acheive the desired proportions
		w = self.width()
		self.resize(self.size())
		self.resizeDocks(
			[second, main, script],
			[int(0.2*w), int(1.5*w), int(0.5*w)],
			Qt.Horizontal,
			)
		
		main.widget().setFocus()
	
	@action(shortcut='Ctrl+Shift+L', icon='madcad-layout-triple')
	def layout_triple(self):
		''' 3 view layout in addition to a script view
			- one main view
			- two orthographic top and side views
		'''
		self._layout_clear()
		
		self.addDockWidget(Qt.TopDockWidgetArea, top := DockedView(SceneView(self.app, projection = Orthographic()), 'top scene view'))
		self.addDockWidget(Qt.TopDockWidgetArea, main := DockedView(SceneView(self.app), 'main scene view'))
		self.addDockWidget(Qt.TopDockWidgetArea, script := DockedView(ScriptView(self.app), 'script view'))
		self.splitDockWidget(top, side := DockedView(SceneView(self.app, projection = Orthographic()), 'side scene view'), Qt.Vertical)
		
		main.widget().orient(fquat(fvec3(+pi/3, 0, -pi/4)))
		top.widget().orient(fquat(fvec3(0)))
		side.widget().orient(fquat(fvec3(pi/2, 0, -pi/2)))
		
		# resize docks, Qt is actuelly very bad at computing layouts, so the sizes here will not be acheived by Qt
		# instead empirical values are provided to acheive the desired proportions
		w = self.width()
		self.resizeDocks(
			[top, side, main, script],
			[int(0.1*w), int(0.1*w), int(2*w), int(0.5*w)],
			Qt.Horizontal,
			)
		h = self.height()
		self.resizeDocks(
			[top, side],
			[int(h//2), int(1*h)],
			Qt.Vertical,
			)
		
		main.widget().setFocus()

	@action(shortcut='Ctrl+Shift+M', icon='madcad-layout-minimal')
	def layout_minimal(self):
		''' minimal layout with only one scene view '''
		self._layout_clear()
		
		self.addDockWidget(Qt.TopDockWidgetArea, main := DockedView(SceneView(self.app), 'scene view'))
		
		main.widget().orient(fquat(fvec3(+pi/3, 0, -pi/4)))
		
		main.widget().setFocus()
	
	@action(icon='madcad-scriptview')
	def new_scriptview(self):
		''' insert a new code view into the window layout 
		
			Controls:
				Backspace	Deletes the character to the left of the cursor.
				Delete	Deletes the character to the right of the cursor.
				Ctrl+C	Copy the selected text to the clipboard.
				Ctrl+Insert	Copy the selected text to the clipboard.
				Ctrl+K	Deletes to the end of the line.
				Ctrl+V	Pastes the clipboard text into text edit.
				Shift+Insert	Pastes the clipboard text into text edit.
				Ctrl+X	Deletes the selected text and copies it to the clipboard.
				Shift+Delete	Deletes the selected text and copies it to the clipboard.
				Ctrl+Z	Undoes the last operation.
				Ctrl+Y	Redoes the last operation.
				Left	Moves the cursor one character to the left.
				Ctrl+Left	Moves the cursor one word to the left.
				Right	Moves the cursor one character to the right.
				Ctrl+Right	Moves the cursor one word to the right.
				Up	Moves the cursor one line up.
				Down	Moves the cursor one line down.
				PageUp	Moves the cursor one page up.
				PageDown	Moves the cursor one page down.
				Home	Moves the cursor to the beginning of the line.
				Ctrl+Home	Moves the cursor to the beginning of the text.
				End	Moves the cursor to the end of the line.
				Ctrl+End	Moves the cursor to the end of the text.
				Alt+Wheel	Scrolls the page horizontally (the Wheel is the mouse wheel).
		'''
		self.addDockWidget(Qt.TopDockWidgetArea, DockedView(ScriptView(self.app), 'script view'))
	
	@action(icon='madcad-sceneview')
	def new_sceneview(self):
		''' insert a new 3d view into the window layout 
		
			Controls:
				MB2   rotate around view center
				MB1   select / interact with objects
				Shift+MB1   select multiple items
				Ctrl+MB1   pan the view
				Alt+MB1   rotate around view center
		'''
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

	@action(icon='view-dual')
	def copy_layout_to_clipboard(self):
		''' dump the layout state to clipboard (for developers) '''
		QApplication.clipboard().setText(str(self.saveState()))
	

class DockedView(QDockWidget):
	''' override dedicated to MainWindow, adding a specific behavior for views with a top toolbar '''
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
			self.restore_button = Button(self.setFloating, flat=True, minimal=True,
					icon='window-restore-symbolic', 
					description="detach view from main window")
			self.close_button = Button(self.close, flat=True, minimal=True,
				icon='window-close-symbolic', 
				description="close view")
			
			title = QWidget()
			title.setLayout(hlayout([
				content.top,
				spacer(5,0),
				self.restore_button,
				self.close_button,
				], spacing=0, margins=(0,0,0,0)))
			self.setTitleBarWidget(title)
			
	def close(self):
		''' the view is not only hidden but also destroyed '''
		self.parent().removeDockWidget(self)
