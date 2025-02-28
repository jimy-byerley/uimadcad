import traceback

from madcad.mathutils import mix
from madcad.qt import (
    Qt, QSizePolicy, QTextCursor, QFont, QPalette, QColor,
    QWidget, QLabel, QTextBrowser, QTimer,
    )
from . import settings
from .utils import (
    PlainTextEdit, Splitter, 
    hlayout, vlayout, 
    button, Initializer, 
    charformat, color_to_vec, vec_to_color,
    )


class ErrorView(QWidget):
	def __init__(self, app, parent=None):
		self.app = app
		self.exception = None
		self.font = QFont(*settings.scriptview['font'])
		
		super().__init__(parent)
		Initializer.process(self)
		
		self.traceback = QTextBrowser()
		self.scope = QTextBrowser()
		self.label = QLabel()
		self.label.setFont(self.font)
		self.label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
		
		self.setLayout(hlayout([
			vlayout([self.keep_apart, self.open_scope]),
			vlayout([self.traceback, self.label]),
			Splitter([
				self.scope,
				], Qt.Horizontal),
			]))
			
		self.open_scope.toggled.emit(False)
		self.clear()
		
	def clear(self):
		''' clear the active exception
		
			- dropping all retained variables 
			- clearing the widgets
		'''
		self.exception = None
		self.label.setText('no exception')
		self.traceback.setPlainText('')
		self.scope.setPlainText('')
			
	def set(self, exception):
		''' set the exception to display '''
		self.exception = exception
		# set labels
		self.setWindowTitle(type(exception).__name__)
		self.label.setText('<b style="color:#ff5555">{}:</b> {}'.format(
			type(exception).__name__, 
			str(exception).replace('<', '&lt;').replace('>', '&gt;'),
			))
		# set text
		document = self.traceback.document()
		document.clear()
		cursor = QTextCursor(document)
		palette = self.palette()
		fmt_traceback = charformat(font=self.font, foreground=palette.color(QPalette.Text))
		fmt_code = charformat(font=self.font, foreground=vec_to_color(mix(
						color_to_vec(palette.color(QPalette.Text)), 
						color_to_vec(palette.color(QPalette.Background)),
						0.5)))
		fmt_error = charformat(font=self.font, background=vec_to_color(mix(
						color_to_vec(QColor(255,100,100)),
						color_to_vec(palette.color(QPalette.Background)),
						0.2)))
		if type(exception) == SyntaxError and exception.filename == self.main.interpreter.name:
			cursor.insertText('  File \"{}\", line {}\n'.format(exception.filename, exception.lineno), fmt_traceback)
			offset = exception.offset
			while offset > 0 and exception.text[offset-1].isalnum():	offset -= 1
			cursor.insertText('    '+exception.text[:offset], fmt_code)
			cursor.insertText(exception.text[offset:], fmt_error)
		else:
			tb = traceback.extract_tb(exception.__traceback__)
			i = next((i for i in range(len(tb)) if tb[i].filename == self.main.interpreter.name), 0)
			for line in traceback.format_list(tb)[i:]:
				if line.startswith('    '):
					cursor.insertText(line, fmt_code)
				else:
					endline = line.find('\n')
					cursor.insertText(line[:endline], fmt_traceback)
					cursor.insertText(line[endline:], fmt_code)
		
		# scroll on the end of the error message (most of the time the most interesting part)
		cursor = self.traceback.textCursor()
		cursor.movePosition(QTextCursor.End)
		self.traceback.setTextCursor(cursor)
		self.traceback.ensureCursorVisible()
		self.setVisible(True)
		
		if type(self.exception) == SyntaxError and self.exception.filename == self.main.interpreter.name:
			self.line = self.exception.lineno
		else:
			step = self.exception.__traceback__
			self.line = -1
			while step:
				if step.tb_frame.f_code.co_filename == self.main.interpreter.name:
					self.line = step.tb_frame.f_lineno
					break
				step = step.tb_next
		
	@button(icon='window-pin', minimal=True, checked=False, flat=True, shortcut='Ctrl+P')
	def keep_apart(self, enable):
		''' show this exception in a separate window to prevent erasing it at the next execution '''
		if self.app.active_errorview is self:
			self.app.active.errorview = ErrorView(self.app)
			self.setParent(None)
			self.show()
		
	@button(icon='view-list-details', checked=False, minimal=True, flat=True, shortcut='Ctrl+V')
	def open_scope(self, visible):
		''' show the variables when selecting a scope in the traceback 
		
			move the cursor in the traceback to select a scope
		'''
		self.scope.setVisible(visible)
		if self.parent():
			QTimer.singleShot(100, self.parent().adjustSize)
		else:
			self.adjustSize()
	
		if visible and self.exception and self.exception.__traceback__:
			n = self._text.textCursor().blockNumber() //2
			
			step = self.exception.__traceback__
			for i in range(n+1):
				if step.tb_next:
					step = step.tb_next
			scope = step.tb_frame.f_locals
		
			self._scope.document().clear()
			cursor = QTextCursor(self._scope.document())
			palette = self.palette()
			familly, size = settings.scriptview['font']
			
			fmt_value = charformat(
							font=QFont(familly, size), 
							foreground=palette.text())
			fmt_key = charformat(
							font=QFont(familly, size*1.2, weight=QFont.Bold), 
							foreground=palette.link())
			
			if isinstance(scope, dict):
				for key in scope:
					formated = nformat(repr(scope[key]))
					# one line format
					if not '\n' in formated:	
						cursor.insertText((key+':').ljust(16), fmt_key)
						cursor.insertText(formated+'\n', fmt_value)
					# multiline format
					else:
						cursor.insertText(key+':', fmt_key)
						cursor.insertText(('\n'+formated).replace('\n', '\n    ')+'\n', fmt_value)
	
	@property
	def keep(self):	
		''' whether the error window is marked to be keept as-is '''
		return self._keepchk.isChecked()
		
	def keyPressEvent(self, evt):
		if evt.key() == Qt.Key_Escape:		self.close()
		
	def closeEvent(self, evt):
		if self.main.active_errorview is self:
			self.main.active_errorview = None
		evt.accept()
