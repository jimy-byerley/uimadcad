from madcad.qt import Qt, QWidget, QLabel, QSizePolicy
from .utils import PlainTextEdit, hlayout, vlayout, button, Splitter, Initializer

class ErrorView(QWidget):
    def __init__(self, app, parent=None):
        self.app = app
        self.exception = None
        
        super().__init__(parent)
        Initializer.process(self)
        
        self.traceback = PlainTextEdit()
        self.scope = PlainTextEdit()
        self.label = QLabel('no exception')
        self.label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        
        self.setLayout(hlayout([
            vlayout([self.keep_apart, self.open_scope]),
            vlayout([self.traceback, self.label]),
            Splitter([
                self.scope,
                ], Qt.Horizontal),
            ]))
            
        self.open_scope.toggled.emit(False)
            
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
        doc.clear()
        cursor = QTextCursor(doc)
        palette = self._text.palette()
        fmt_traceback = charformat(font=self.font, foreground=palette.color(QPalette.Text))
        fmt_code = charformat(font=self.font, foreground=mixcolors(
                        palette.color(QPalette.Text), 
                        palette.color(QPalette.Background),
                        0.5))
        fmt_error = charformat(font=self.font, background=mixcolors(
                        QColor(255,100,100),
                        palette.color(QPalette.Background),
                        0.2))
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
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()
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
                
        self._sourcebtn.setVisible(self.line >= 0)
        
    @button(icon='window-pin', minimal=True, checked=False, shortcut='Ctrl+P')
    def keep_apart(self, enable):
        ''' show this exception in a separate window to prevent erasing it at the next execution '''
        if self.app.active_errorview is self:
            self.app.active.errorview = ErrorView(self.app)
            self.setParent(None)
            self.show()
        
    @button(icon='view-list-details', checked=False, minimal=True, shortcut='Ctrl+V')
    def open_scope(self, visible):
        self.scope.setVisible(visible)
    
        if visible and self.exception and self.exception.__traceback__:
            n = self._text.textCursor().blockNumber() //2
            print(self._text.textCursor().blockNumber() , n)
            
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
