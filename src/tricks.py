from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QTextCursor
from madcad.mathutils import vec3
import re, ast
from madcad.displays import *
from nprint import nprint



format_varname = r'[a-zA-Z]\w*'
format_float = r'[+-]?\d+\.?\d*(?:e[+-]?\d+)?'
format_vec3 = r'vec3\(\s*({0}),\s*({0}),\s*({0}),?\s*\)'.format(format_float)
format_axis = r'\({0},\s{0}\)'.format(format_vec3)
edit_color = fvec3(1, 0.8, 0.2)
edit_text = 8


class EditionError(Exception):	pass

class EditorNode:
	''' base class the simplify the implementation of editors based on a text node '''
	def __init__(self, main, name):
		self.main = main
		self.name = name
		self.point = main.scene[name]
		
		node = main.interpreter.locations[name]
		if isinstance(node, ast.Assign):	node = node.value
		
		cursor = QTextCursor(self.main.script)
		cursor.setPosition(node.end_position)
		cursor.setPosition(node.position, QTextCursor.KeepAnchor)
		self.cursor = cursor
		
	def apply(self):
		''' update the script with the modifications '''
		pos = min(self.cursor.anchor(), self.cursor.position())
		self.cursor.beginEditBlock()
		self.cursor.removeSelectedText()
		self.cursor.insertText(self.dump())
		self.cursor.setPosition(pos, QTextCursor.KeepAnchor)
		self.cursor.endEditBlock()
		
	def finish(self):
		pass
		
def store(dst, src):
	for i in range(len(dst)):
		dst[i] = src[i]

class PointEditor(EditorNode):
	''' editor for a single point position '''
	def __init__(self, main, name):
		super().__init__(main, name)
		if not re.fullmatch(format_vec3, self.cursor.selectedText()):
			raise EditionError("the current expression format can't be edited")
	
	def dump(self):
		return 'vec3({:.5g}, {:.5g}, {:.5g})'.format(*self.point)
	
	def display(self, scene):
		return self.Display(scene, self),
	
	class Display(PointDisplay):
		def __init__(self, scene, editor):
			super().__init__(scene, editor.point, color=edit_color)
			self.editor = editor
		def control(self, scene, rdri, ident, evt):
			self.startpt = vec3(self.editor.point)
			return self.move
		def move(self, scene, evt):
			if evt.type() == QEvent.MouseMove:
				store(self.editor.point, scene.ptfrom((evt.x(), evt.y()), self.startpt))
				self.position = fvec3(self.editor.point)
				scene.update()
			else:
				self.editor.apply()
				scene.tool = None
				if self.editor.main.exectrigger:
					self.editor.main.execute()
			return True


class MeshEditor(EditorNode):
	format = re.compile(r'Mesh\(\s\[((\s{},\s)*)\], \[((\s\d\s,)*\)])'.format(format_vec3))
	
