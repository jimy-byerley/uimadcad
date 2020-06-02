from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QTextCursor
from madcad.mathutils import vec3
import re
from madcad.displays import *



format_varname = r'[a-zA-Z]\w*'
format_float = r'[+-]?\d+\.?\d*(?:e[+-]?\d+)?'
format_vec3 = r'vec3\(\s*({0}),\s*({0}),\s*({0}),?\s*\)'.format(format_float)
format_axis = r'\({0},\s{0}\)'.format(format_vec3)
trick_color = fvec3(255, 200, 80)
trick_text = 8

		
def store(dst, src):
	for i in range(len(dst)):
		dst[i] = src[i]

class Assign:
	format = re.compile(format_varname+r'\s=\s')
	def __init__(self, varname, expr):
		self.varname, self.expr = varname, expr
	@staticmethod
	def fromexpr(groups):
		indev
	def display(self, scene):
		yield from self.expr.display(scene)
		yield Text(expr.box().max, self.varname, 7)

class Trick:
	def __init__(self, main, found=None):
		self.main = main
		if found:	self.found(found)
	def updatetext(self):
		pos = min(self.cursor.anchor(), self.cursor.position())
		self.cursor.removeSelectedText()
		dump = str(self)
		self.cursor.insertText(dump)
		self.cursor.setPosition(pos, QTextCursor.KeepAnchor)

class ControledPoint(Trick):
	format = re.compile(format_vec3)
	def found(self, found):
		self.point = vec3()
		for i in range(3):
			self.point[i] = float(found.group(i+1))
	def __str__(self):
		return 'vec3({}, {}, {})'.format(*self.point)
	def display(self, scene):
		return self.Display(scene, self),
	
	class Display(PointDisplay):
		def __init__(self, scene, trick):
			super().__init__(scene, trick.point, color=trick_color)
			self.trick = trick
		def control(self, scene, grp, ident, evt):
			self.trick.cursor.beginEditBlock()
			self.startpt = vec3(self.trick.point)
			return self.move
		def move(self, scene, evt):
			if evt.type() == QEvent.MouseMove:
				store(self.trick.point, scene.ptfrom((evt.x(), evt.y()), self.startpt))
				self.trick.updatetext()
			else:
				self.trick.updatetext()
				self.trick.cursor.endEditBlock()
				scene.tool = None
				if self.trick.main.exectrigger == 1:
					self.trick.main.execute()
			return True

class ControledAxis(Trick):
	format = re.compile(format_axis)
	def found(self, found):
		print(found)
		self.axis = (vec3(), vec3())
		for j in range(2):
			for i in range(3):
				self.axis[j][i] = float(found.group(3*j+i+1))
		print('got', self.axis)
	def __str__(self):
		return '(vec3({}, {}, {}), vec3({}, {}, {}))'.format(*self.axis[0], *self.axis[1])
	def display(self, scene):
		return AxisDisplay(scene, self.axis, color=trick_color),


class Revolution(Trick):
	format = re.compile(r'revolution\(')
	def find(self, text, line):
		found = self.format.search(text)
		if found:
			args = []
			start = found.end()
			while start != len(text):
				end = expressionend(text, start)
				args.append(text[start:end])
			interpreter = self.main.interpreter
			self.angle = interpreter.eval(line, args[0])
			self.axis = interpreter.eval(line, args[1])
			self.shape = interpreter.eval(line, args[2])
			self.args = args
			
	def updatetext(self):	pass
	def display(self, scene):
		yield AxisDisplay(scene, self.axis, color=trick_color),
		yield TextDisplay(scene, self.axis[0], self.args[1], trick_text, color=trick_color)
		yield from ArcMeasure(Arc(self.axis, ptmax, ptrot), self.args[0], arrows=0b01, color=trick_color).display()
		yield from self.shape.display(scene)

class MeshTrick:
	format = re.compile(r'Mesh\(\s\[((\s{},\s)*)\], \[((\s\d\s,)*\)])'.format(format_vec3))
	def __init__(self, mesh):
		self.mesh = mesh
	@classmethod
	def found(cls, found):
		print(found.groups(0))
