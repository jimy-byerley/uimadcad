''' collection of helpers to deal with Qt
'''
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCharFormat, QTextCursor, QColor
from PyQt5.QtWidgets import QDockWidget, QTextEdit

import sys, os

# determine the current software's ressource directory
ressourcedir = os.path.abspath(__file__ + '/..')


def propertywrite(func):
	''' decorator to create a property with only a write function '''
	fieldname = '_'+func.__name__
	def getter(self):	return getattr(self, fieldname)
	def setter(self, value):
		setattr(self, fieldname, value)
		func(self, value)
	return property(getter, setter)

def charformat(background=None, foreground=None, italic=None, overline=None, strikeout=None, weight=None, font=None):
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

def mixcolors(a, b, x):
	a = a.toRgb()
	b = b.toRgb()
	y = 1-x
	return QColor(
		int(a.red()*x + b.red()*y),
		int(a.green()*x + b.green()*y),
		int(a.blue()*x + b.blue()*y),
		)


def cursor_location(cursor):
	return cursor.blockNumber(), cursor.positionInBlock()

def move_text_cursor(cursor, location, movemode=QTextCursor.MoveAnchor):
	line, column = location
	if cursor.blockNumber() < line:		cursor.movePosition(cursor.NextBlock, movemode, line-cursor.blockNumber())
	if cursor.blockNumber() < line:		cursor.movePosition(cursor.PreviousBlock, movemode, cursor.blockNumber()-line)
	if cursor.columnNumber() < column:	cursor.movePosition(cursor.NextCharacter, movemode, column-cursor.columnNumber())
	if cursor.columnNumber() > column:	cursor.movePosition(cursor.PreviousCharacter, movemode, cursor.columnNumber()-column)



def extraselection(cursor, format):
	''' create an ExtraSelection '''
	o = QTextEdit.ExtraSelection()
	o.cursor = cursor
	o.format = format
	return o
		

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

	
class NoBackDock(QDockWidget):
	def closeEvent(self, evt):
		super().closeEvent(evt)
		self.parent().removeDockWidget(self)
		evt.accept()
