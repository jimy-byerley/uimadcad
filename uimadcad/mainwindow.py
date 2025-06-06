import warnings
import sys
import os
from functools import partial
from time import time

from madcad.qt import (
	Qt, QApplication, 
	QWidget, QMainWindow, QDockWidget, QLabel, QGroupBox,
	QShortcutEvent, QEvent,
	QTimer, QPainter, QColor, QPalette, QSize, QRectF, QPoint,
	)
from madcad.rendering import Orthographic
from madcad.mathutils import fvec3, fquat, pi

from . import settings
from .sceneview import SceneView
from .scriptview import ScriptView
from .errorview import ErrorView
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
		
		self.panel = ExecutionPanel(self.app, self)
		
		self.toolbar_execute = ToolBar('execution', [
			self.app.execute,
			self.app.clear,
			self.open_panel,
			self.app.trigger_on_file_change,
			None,
			self.app.open_uimadcad_settings,
			self.app.open_pymadcad_settings,
			])
		self.addToolBar(Qt.LeftToolBarArea, ToolBar('file', [
			self.app.save,
			self.app.save_as,
			self.app.open,
			self.app.new,
			]))
		self.addToolBar(Qt.LeftToolBarArea, self.toolbar_execute)
		self.addToolBar(Qt.LeftToolBarArea, ToolBar('windowing', [
			self.new_sceneview,
			self.new_scriptview,
			# self.copy_layout_to_clipboard,
			None,
			# Button(icon = 'view-dual', 
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
		self.open_panel.toggled.emit(False)
		
	def keyPressEvent(self, event):
		event.accept()
		# reimplement top bar shortcuts here because Qt cannot deambiguate which view the shortcut belongs to
		if event.key() == Qt.Key_Escape:
			self._focus_other()
		else:
			event.ignore()
			return super().keyPressEvent(event)
			
	def resizeEvent(self, event):
		super().resizeEvent(event)
		margin = 3
		self.panel.setGeometry(
			self.toolbar_execute.width() + margin, self.height()//2 - self.panel.sizeHint().height()//2,
			min(self.panel.sizeHint().width(), self.width() - self.toolbar_execute.width() - 2*margin), 
			min(self.panel.sizeHint().height(), self.height() - 2*margin),
			)
	
	def changeEvent(self, event):
		# window activation should trigger execution if enabled
		if event.type() == QEvent.ActivationChange and self.isActiveWindow():
			self.app.check_change()
	
	# @shortcut(shortcut='Esc')
	def _focus_other(self):
		''' switch focus between active sceneview and active scriptview  '''
		active = self.app.active
		if self.app.window.panel.isVisible():
			self.app.window.open_panel.setChecked(False)
		elif active.sceneview and not active.sceneview.hasFocus():
			active.sceneview.setFocus()
		elif active.scriptview and not active.scriptview.hasFocus():
			active.scriptview.setFocus()
			active.scriptview.editor.ensureCursorVisible()
	
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
	
	@action(icon='application-menu', checked=False, shortcut='Ctrl+Shift+Return')
	def open_panel(self, visible):
		''' open the status panel
		
			- if an execution is running, it presents the scopes progression bars
			- if the last execution failed, it shows its traceback
		'''
		self.panel.setVisible(visible)
		self.panel.adjustSize()
		self.panel.raise_()
		
	def clear_panel(self, widget: QWidget):
		''' hide the panel if the given widget is below '''
		if not self.panel.isVisible():
			return
		panel = QRectF(
			self.panel.mapToGlobal(QPoint(0,0)),
			self.panel.mapToGlobal(QPoint(self.panel.width(), self.panel.height())),
			)
		widget = QRectF(
			widget.mapToGlobal(QPoint(0,0)),
			widget.mapToGlobal(QPoint(widget.width(), widget.height())),
			)
		if panel.intersects(widget):
			self.open_panel.setChecked(False)


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
		self.setContentsMargins(1,1,1,1)
		
		if isinstance(getattr(content, 'top', None), QWidget):
			self.restore_button = Button(self.setFloating, flat=True, minimal=True,
					icon='window-restore', 
					description="detach view from main window")
			self.close_button = Button(self.close, flat=True, minimal=True,
				icon='window-close', 
				description="close view")
			
			title = QWidget()
			title.setLayout(hlayout([
				content.top,
				spacer(5,0),
				self.restore_button,
				self.close_button,
				], spacing=0, margins=(0,0,0,0)))
			self.setTitleBarWidget(title)
	
	def paintEvent(self, event):
		painter = QPainter(self)
		painter.setRenderHint(QPainter.Antialiasing, True)
		pen = painter.pen()
		pen.setColor(self.palette().midlight().color())
		pen.setWidth(1)
		painter.setPen(pen)
		radius = 2
		painter.drawRoundedRect(QRectF(0.5, 0.5, self.width()-1, self.height()-1), radius, radius)
			
	def close(self):
		''' the view is not only hidden but also destroyed '''
		self.parent().removeDockWidget(self)

	
class ExecutionPanel(QGroupBox):
	def __init__(self, app, parent=None):
		self.app = app
		
		super().__init__(parent)
	
		self.ring = MultiRing(150)
		self.status = QLabel()
		self.errorview = ErrorView(self.app)
		self.stop = Button(self.app.stop.trigger, 
			icon = self.app.stop.icon(),
			description = self.app.stop.toolTip(),
			flat = True,
			parent=self)
		
		self.setLayout(hlayout([
			self.ring,
			self.status,
			self.errorview,
			]))
		self.stop.raise_()
		
		self.app.active.errorview = self.errorview
		self.set_success()
		
	def resizeEvent(self, event):
		super().resizeEvent(event)
		self.stop.setGeometry(
			self.ring.x() + self.ring.width()//2 - self.stop.sizeHint().width()//2,
			self.ring.y() + self.ring.height()//2 - self.stop.sizeHint().height()//2,
			self.stop.sizeHint().width(),
			self.stop.sizeHint().height(),
			)
	
	def set_exception(self, exception):
		''' show the given exception with its traceback in the status panel '''
		self.stop.setEnabled(False)
		self.status.hide()
		self.errorview.show()
		self.errorview.set(exception)
		self.ring.progressing = False
		self.ring.color = QColor(255, 0, 0)
		self.ring.update()
		self.adjustSize()
		self.adjustSize()
		
	def set_progress(self, progress):
		''' show the given execution progress in the status panel '''
		self.errorview.hide()
		self.status.show()
		self.stop.setEnabled(True)
		self.ring.progressing = True
		self.ring.progress = [progress 
			for scope, progress in progress.items() 
			if progress < 1. ]
		self.status.setText('\n'.join('{}: {}%'.format(scope, int(progress*100))  
			for scope, progress in progress.items()
			if progress < 1. ))
		self.ring.color = self.palette().color(QPalette.Active, QPalette.Highlight)
		self.ring.update()
		self.adjustSize()
		
	def set_success(self):
		''' show that last execution was successfull in the status panel '''
		self.stop.setEnabled(False)
		self.errorview.hide()
		self.status.show()
		self.status.setText('calculation succeed\n100%')
		self.ring.progress = [1.]
		self.ring.progressing = False
		self.ring.color = QColor(0, 255, 0)
		self.ring.update()
		self.adjustSize()

class MultiRing(QWidget):
	''' progress ring '''
	line_width = 1
	bar_width = 5
	radius_exterior = 0.9
	radius_step = 0.1
	radius_interior = 0.3
	move_frequency = 0.5

	def __init__(self, size, color=None, parent=None):
		self.size = size
		self.progress = [1.]
		self.progressing = False
		self.color = color
		super().__init__(parent)
		
		# refresh periodically
		self.timer = QTimer(self)
		self.timer.setInterval(30)
		self.timer.timeout.connect(self.update)
		
	def sizeHint(self):
		return QSize(self.size, self.size)
		
	def paintEvent(self, event):
		size = min(self.width(), self.height())
		turn = 5760 # number of increments per turn, from QPainter docs
		start = 0.75 # start point is bottom
		
		if self.progressing and not self.timer.isActive():
			self.timer.start()
		elif not self.progressing and self.timer.isActive():
			self.timer.stop()
		
		painter = QPainter(self)
		painter.setRenderHints(QPainter.Antialiasing, True)
		pen = painter.pen()
		
		# represent scopes in insertion order
		scale = self.radius_exterior
		for i, progress in enumerate(self.progress):
			# draw progress ring
			progress_radius = int(scale * size/2)
			color_bar = self.color or self.palette().color(QPalette.WindowText)
			color_line = QColor(color_bar.red(), color_bar.green(), color_bar.blue(), 100)
			
			pen.setWidth(self.line_width)
			pen.setColor(color_line)
			painter.setPen(pen)
			painter.drawEllipse(
				self.width()//2 - progress_radius, self.height()//2 - progress_radius, 
				2*progress_radius, 2*progress_radius,
				)
			pen.setWidth(self.bar_width)
			pen.setColor(color_bar)
			painter.setPen(pen)
			painter.drawArc(
				self.width()//2 - progress_radius, self.height()//2 - progress_radius, 
				2*progress_radius, 2*progress_radius,
				int(turn*start), int(turn*-progress),
				)
			# radius for next bar
			scale -= self.radius_step
			if scale <= self.radius_interior:
				break
		
		# draw always rotating ring
		move_radius = int(scale * size/2)
		color_bar = self.palette().color(QPalette.WindowText)
		color_line = QColor(color_bar.red(), color_bar.green(), color_bar.blue(), 100)
		
		pen.setWidth(self.line_width)
		pen.setColor(color_line)
		painter.setPen(pen)
		painter.drawEllipse(
			self.width()//2 - move_radius, self.height()//2 - move_radius, 
			2*move_radius, 2*move_radius,
			)
		if self.progressing:
			pen.setWidth(self.bar_width)
			pen.setColor(color_bar)
			painter.setPen(pen)
			painter.drawArc(
				self.width()//2 - move_radius, self.height()//2 - move_radius, 
				2*move_radius, 2*move_radius,
				int(turn*(start - self.move_frequency*time() % 1)), int(turn*0.3),
				)


class Ring(QWidget):
	''' progress ring '''
	line_width = 1
	bar_width = 5
	exterior_scale = 0.9
	interior_scale = 0.7
	move_frequency = 0.5

	def __init__(self, size, color=None, parent=None):
		self.size = size
		self.progress = 0.
		self.progressing = False
		self.color = color
		super().__init__(parent)
		
		# refresh periodically
		self.timer = QTimer(self)
		self.timer.setInterval(30)
		self.timer.timeout.connect(self.update)
		
	def sizeHint(self):
		return QSize(self.size, self.size)
		
	def paintEvent(self, event):
		size = min(self.width(), self.height())
		move_radius = int(self.interior_scale * size/2)
		progress_radius = int(self.exterior_scale * size/2)
		turn = 5760 # number of increments per turn, from QPainter docs
		start = 0.75 # start point is bottom
		
		if self.progressing and not self.timer.isActive():
			self.timer.start()
		elif not self.progressing and self.timer.isActive():
			self.timer.stop()
		
		painter = QPainter(self)
		painter.setRenderHints(QPainter.Antialiasing, True)
		pen = painter.pen()
		# draw progress ring
		color_bar = self.color or self.palette().color(QPalette.WindowText)
		color_line = QColor(color_bar.red(), color_bar.green(), color_bar.blue(), 100)
		pen.setWidth(self.line_width)
		pen.setColor(color_line)
		painter.setPen(pen)
		painter.drawEllipse(
			self.width()//2 - progress_radius, self.height()//2 - progress_radius, 
			2*progress_radius, 2*progress_radius,
			)
		pen.setWidth(self.bar_width)
		pen.setColor(color_bar)
		painter.setPen(pen)
		painter.drawArc(
			self.width()//2 - progress_radius, self.height()//2 - progress_radius, 
			2*progress_radius, 2*progress_radius,
			int(turn*start), int(turn*-self.progress),
			)
		# draw always rotating ring
		
		color_bar = self.palette().color(QPalette.WindowText)
		color_line = QColor(color_bar.red(), color_bar.green(), color_bar.blue(), 100)
		pen.setWidth(self.line_width)
		pen.setColor(color_line)
		painter.setPen(pen)
		painter.drawEllipse(
			self.width()//2 - move_radius, self.height()//2 - move_radius, 
			2*move_radius, 2*move_radius,
			)
		if self.progressing:
			pen.setWidth(self.bar_width)
			pen.setColor(color_bar)
			painter.setPen(pen)
			painter.drawArc(
				self.width()//2 - move_radius, self.height()//2 - move_radius, 
				2*move_radius, 2*move_radius,
				int(turn*(start - self.move_frequency*time() % 1)), int(turn*0.3),
				)
