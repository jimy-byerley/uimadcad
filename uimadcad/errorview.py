import traceback
from bisect import bisect
from types import FunctionType, BuiltinFunctionType

from pnprint import nformat
from madcad.mathutils import mix
from madcad.qt import (
    Qt, QSizePolicy, QTextCursor, QFont, QPalette, QColor, QSize,
    QApplication, QWidget, QLabel, QTextBrowser, QTimer, QTextEdit,
    )
from . import settings
from .utils import (
    PlainTextEdit, Splitter, 
    hlayout, vlayout, widget,
    button, Initializer, 
    charformat, qcolor_to_vec, vec_to_qcolor,
    )


class ErrorView(QWidget):
	def __init__(self, app, parent=None):
		self.app = app
		self.exception = None
		self.font = QFont(*settings.scriptview['font'])
		self._index = [] # end text position of each scope in displayed order
		
		super().__init__(parent)
		Initializer.process(self)
		
		self.traceback = QTextBrowser()
		self.scope = QTextBrowser()
		self.label = QLabel()
		
		self.traceback.setLineWrapMode(QTextEdit.NoWrap)
		self.scope.setLineWrapMode(QTextEdit.NoWrap)
		self.traceback.cursorPositionChanged.connect(self._update_scope)
		self.traceback.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		self.scope.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		self.label.setFont(self.font)
		self.label.setWordWrap(True)
		self.label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
		self.label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		
		self.setLayout(hlayout([
			vlayout([self.keep_apart, self.copy_to_clipboard, self.open_scope]),
			Splitter([
				widget(vlayout([self.traceback, self.label], margins=0)),
				self.scope,
				], Qt.Horizontal),
			], margins=0))
			
		self.open_scope.toggled.emit(False)
		self.clear()
		
	def sizeHint(self):
		return QSize(self.font.pointSize()*80, self.font.pointSize()*20)
		
	def clear(self):
		''' clear the active exception
		
			- dropping all retained variables 
			- clearing the widgets
		'''
		self.exception = None
		self.label.setText('no exception')
		self.traceback.setPlainText('')
		self.scope.setPlainText('')
		self._index.clear()
			
	def set(self, exception):
		''' set the exception to display '''
		self._index.clear()
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
		fmt_code = charformat(font=self.font, foreground=vec_to_qcolor(mix(
						qcolor_to_vec(palette.color(QPalette.Text)), 
						qcolor_to_vec(palette.color(QPalette.Window)),
						0.5)))
		fmt_error = charformat(font=self.font, background=vec_to_qcolor(mix(
						qcolor_to_vec(QColor(255,100,100)),
						qcolor_to_vec(palette.color(QPalette.Window)),
						0.2)))
		if type(exception) == SyntaxError and exception.filename == self.app.interpreter.filename:
			cursor.insertText('  File \"{}\", line {}\n'.format(exception.filename, exception.lineno), fmt_traceback)
			if exception.text:
				offset = exception.offset
				while offset > 0 and exception.text[offset-1].isalnum():	offset -= 1
				cursor.insertText('    '+exception.text[:offset], fmt_code)
				cursor.insertText(exception.text[offset:], fmt_error)
				self._index.append(cursor.position())
		else:
			tb = traceback.extract_tb(exception.__traceback__)
			i = next((i for i in range(len(tb)) if tb[i].filename == self.app.interpreter.filename), 0)
			for line in traceback.format_list(tb)[i:]:
				if line.startswith('    '):
					cursor.insertText(line, fmt_code)
					self._index.append(cursor.position())
				else:
					endline = line.find('\n')
					cursor.insertText(line[:endline], fmt_traceback)
					cursor.insertText(line[endline:], fmt_code)
					self._index.append(cursor.position())
		
		# scroll on the end of the error message (most of the time the most interesting part)
		cursor = self.traceback.textCursor()
		cursor.movePosition(QTextCursor.End)
		self.traceback.setTextCursor(cursor)
		self.traceback.ensureCursorVisible()
		self.setVisible(True)
		
		if type(self.exception) == SyntaxError and self.exception.filename == self.app.interpreter.filename:
			self.line = self.exception.lineno
		else:
			step = self.exception.__traceback__
			self.line = -1
			while step:
				if step.tb_frame.f_code.co_filename == self.app.interpreter.filename:
					self.line = step.tb_frame.f_lineno
					break
				step = step.tb_next
		
	@button(icon='window-pin', minimal=True, flat=True, shortcut='Ctrl+P')
	def keep_apart(self):
		''' show this exception in a separate window to prevent erasing it at the next execution '''
		if self.app.active.errorview is self:
			new = ErrorView(self.app)
			new.set(self.exception)
			new.show()
			
	@button(icon='edit-copy', minimal=True, flat=True, shortcut='Ctrl+C')
	def copy_to_clipboard(self):
		''' copy error message to clipboard (exception and traceback) '''
		QApplication.instance().clipboard().setText(self.traceback.toPlainText() + '\n' + self.label.text())
		
	@button(icon='view-list-details', checked=False, minimal=True, flat=True, shortcut='Ctrl+V')
	def open_scope(self, visible):
		''' show the variables when selecting a scope in the traceback 
		
			move the cursor in the traceback to select a scope
		'''
		if visible and self.exception and self.exception.__traceback__:
			self._update_scope()
		else:
			self.traceback.setFocus()
		
		self.scope.setVisible(visible)
		
	def _update_scope(self):
		''' refresh the content of the scope view '''
		if not self.exception:
			return
		
		n = bisect(self._index, self.traceback.textCursor().position())
			
		step = self.exception.__traceback__
		for i in range(n+1):
			if step.tb_next:
				step = step.tb_next
		scope = step.tb_frame.f_locals
	
		self.scope.document().clear()
		cursor = QTextCursor(self.scope.document())
		palette = self.palette()
		familly, size = settings.scriptview['font']
		
		fmt_value = charformat(
						font=QFont(familly, size), 
						foreground=palette.text())
		fmt_key = charformat(
						font=QFont(familly, int(size*1.2), weight=QFont.Bold), 
						foreground=palette.link())
		fmt_error = charformat(
						font=QFont(familly, int(size*1.2), weight=QFont.Bold), 
						foreground=QColor(255,0,0))
		
		if isinstance(scope, dict):
			for key, value in scope.items():
				if key.startswith('_'):
					continue
				if isinstance(value, (type, FunctionType, BuiltinFunctionType)) and value.__module__ != self.app.interpreter.filename:
					continue
				if isinstance(value, (type, FunctionType)):
					print('value', value.__module__)
				# repr may be user code, so take care of possible failures
				try:
					formated = nformat(repr(value))
				except Exception as err:
					cursor.insertText((key+':').ljust(16), fmt_key)
					cursor.insertText(object.__repr__(value)+'\n', fmt_error)
					continue
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
		if self.app.active.errorview is self:
			self.app.active.errorview = None
		evt.accept()
