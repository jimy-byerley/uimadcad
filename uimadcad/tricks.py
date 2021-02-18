from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QTextCursor
from madcad.mathutils import vec3, affineInverse
import re, ast

from madcad import *
from madcad.displays import *
from madcad.nprint import nprint



format_varname = r'[a-zA-Z]\w*'
format_float = r'[+-]?\d+\.?\d*(?:e[+-]?\d+)?'
format_vec3 = r'vec3\(\s*({0}),\s*({0}),\s*({0}),?\s*\)'.format(format_float)
format_axis = r'(Axis)?\({0},\s{0}\)'.format(format_vec3)
edit_color = fvec3(1, 0.8, 0.2)


class EditionError(Exception):	pass

class EditorNode:
	''' base class the simplify the implementation of editors based on an AST node '''
	def __init__(self, main, name):
		self.main = main
		self.name = name
		
		node = main.interpreter.locations[name]
		if isinstance(node, ast.Assign):	node = node.value
		
		# double cursor to allow undo without loosing the start/end positions in the text
		start = QTextCursor(self.main.script)
		start.setPosition(node.position-1)
		stop = QTextCursor(start)
		stop.setPosition(node.end_position+1)
		self.cursors = (start, stop)
		
		self.load(node)
		
	def cursor(self):
		''' text cursor with the node text selected '''
		start, stop = self.cursors
		cursor = QTextCursor(start)
		cursor.setPosition(start.position()+1)
		cursor.setPosition(stop.position()-1, QTextCursor.KeepAnchor)
		return cursor
		
	def text(self):
		''' get the node text in the script '''
		return self.cursor().selectedText().replace('\u2029', '\n')
		
	def apply(self, run=True):
		''' update the script with the modifications '''
		self.cursor().insertText(self.dump())
		
		if run and self.main.exectrigger:
			self.main.execute()
		
	def finalize(self):
		''' finish the edition '''
		pass
		
def store(dst, src):
	for i in range(len(dst)):
		dst[i] = src[i]

class PointEditor(EditorNode):
	''' editor for a single point position '''
	def load(self, node):
		if not re.fullmatch(format_vec3, self.text()):
			raise EditionError("the current expression format cannot be edited")
		self.point = fvec3(self.main.interpreter.current[self.name])
	
	def dump(self):
		return 'vec3({:.4g}, {:.4g}, {:.4g})'.format(*self.point)
	
	class display(PointDisplay):
		def __init__(self, scene, editor):
			super().__init__(scene, editor.point, color=edit_color)
			self.editor = editor
		def control(self, view, key, sub, evt):
			self.editor.main.active_editor = self.editor
			if evt.type() == QEvent.MouseButtonPress:
				evt.accept()
				self.startpt = fvec3(self.world * fvec4(self.position,1))
				def move(evt):
					if evt.type() == QEvent.MouseMove:
						evt.accept()
						worldpt = fvec3(view.ptfrom(evt.pos(), self.startpt))
						self.editor.point = self.position = fvec3(affineInverse(self.world) * fvec4(worldpt,1))
						view.update()
					else:
						self.editor.apply()
						view.tool.remove(move)
				view.tool.append(move)


class MeshEditor(EditorNode):
	format = re.compile(r'Mesh\(\s\[((\s{},\s)*)\], \[((\s\d\s,)*\)])'.format(format_vec3))
	
editors = {
	vec3:	PointEditor,
	Mesh:	MeshEditor,
	}
