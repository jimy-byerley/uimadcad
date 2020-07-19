from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QTextCursor
from madcad.mathutils import vec3, affineInverse
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
	''' base class the simplify the implementation of editors based on an AST node '''
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
		return 'vec3({:.4g}, {:.4g}, {:.4g})'.format(*self.point)
	
	def display(self, scene):
		return self.Display(scene, self),
	
	class Display(PointDisplay):
		def __init__(self, scene, editor):
			super().__init__(scene, editor.point, color=edit_color)
			self.editor = editor
			self.transform = fmat4(editor.main.poses[editor.name].pose())
		def control(self, scene, rdri, ident, evt):
			if evt.type() == QEvent.MouseButtonPress:
				evt.accept()
				self.startpt = fvec3(self.transform * fvec4(self.position,1))
				return self.move
		def select(self, idents, state=None):
			pass
		def move(self, scene, evt):
			if evt.type() == QEvent.MouseMove:
				evt.accept()
				worldpt = fvec3(scene.ptfrom((evt.x(), evt.y()), self.startpt))
				self.position = fvec3(affineInverse(self.transform) * fvec4(worldpt,1))
				store(self.editor.point, vec3(self.position))
				scene.update()
			else:
				self.editor.apply()
				scene.tool = None
				if self.editor.main.exectrigger:
					self.editor.main.execute()


class MeshEditor(EditorNode):
	format = re.compile(r'Mesh\(\s\[((\s{},\s)*)\], \[((\s\d\s,)*\)])'.format(format_vec3))
	
