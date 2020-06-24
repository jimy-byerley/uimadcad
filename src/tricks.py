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
trick_color = fvec3(1, 0.8, 0.2)
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
	def __init__(self, main, node):
		self.main = main
		self.cursor = QTextCursor(self.main.script)
		self.cursor.setPosition(node.end_position)
		self.cursor.setPosition(node.position, QTextCursor.KeepAnchor)
	def updatetext(self):
		self.cursor.beginEditBlock()
		pos = min(self.cursor.anchor(), self.cursor.position())
		self.cursor.removeSelectedText()
		dump = str(self)
		self.cursor.insertText(dump)
		self.cursor.setPosition(pos, QTextCursor.KeepAnchor)
		self.cursor.endEditBlock()

class ControledPoint(Trick):
	@classmethod
	def match(cls, main, node):
		if node:
			nprint('node', ast.dump(node))
		if not (	isinstance(node, ast.Call) 
				and isinstance(node.func, ast.Name) 
				and node.func.id == 'vec3' 
				and len(node.args) == 3):
			return
		for arg in node.args:
			if not isinstance(arg, ast.Num):	return
		return cls(main, node)
		
	def __init__(self, main, node):
		super().__init__(main, node)
		self.point = vec3()
		for i,arg in enumerate(node.args):
			self.point[i] = arg.n
	def __str__(self):
		return 'vec3({}, {}, {})'.format(*self.point)
	def display(self, scene):
		return self.Display(scene, self),
	
	class Display(PointDisplay):
		def __init__(self, scene, trick):
			super().__init__(scene, trick.point, color=trick_color)
			self.trick = trick
		def control(self, scene, rdri, ident, evt):
			self.startpt = vec3(self.trick.point)
			return self.move
		def move(self, scene, evt):
			if evt.type() == QEvent.MouseMove:
				store(self.trick.point, scene.ptfrom((evt.x(), evt.y()), self.startpt))
				self.position = fvec3(self.trick.point)
				scene.update()
			else:
				self.trick.updatetext()
				scene.tool = None
				if self.trick.main.exectrigger == 1:
					self.trick.main.execute()
			return True
			
class PointEditor:
	def __init__(self, main, name):
		self.main = main
		self.name = name
		self.point = main.scene[name]
		
		node = main.interpreter.locations[name]
		if isinstance(node, ast.Assign):	node = node.value
		
		if not re.fullmatch(format_vec3, self.main.interpreter.text[node.position:node.end_position]):
			raise EditionError("the current expression format can't be edited")
		
		cursor = QTextCursor(self.main.script)
		cursor.setPosition(node.end_position)
		cursor.setPosition(node.position, QTextCursor.KeepAnchor)
		self.cursor = cursor
	
	def dump(self):
		return 'vec3({:.5g}, {:.5g}, {:.5g})'.format(*self.point)
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
	
	def display(self, scene):
		return self.Display(scene, self),
	
	class Display(PointDisplay):
		def __init__(self, scene, trick):
			super().__init__(scene, trick.point, color=trick_color)
			self.trick = trick
		def control(self, scene, rdri, ident, evt):
			self.startpt = vec3(self.trick.point)
			return self.move
		def move(self, scene, evt):
			if evt.type() == QEvent.MouseMove:
				store(self.trick.point, scene.ptfrom((evt.x(), evt.y()), self.startpt))
				self.position = fvec3(self.trick.point)
				scene.update()
			else:
				self.trick.apply()
				scene.tool = None
				if self.trick.main.exectrigger:
					self.trick.main.execute()
			return True

class EditionError(Exception):	pass

class PointEditor2:
	def __init__(self, main, obj):
		''' create an editor object, modifying the view for the purpose (hidding, or changing color) '''
		self.main = main
		self.objname = obj
		self.point = main.scene[obj]
		self.position = fvec3(self.point)
		
		node = self.main.interpreter.locations[self.objname]
		if isinstance(node, ast.Assign):	node = node.value
		cursor = QTextCursor(self.main.script)
		cursor.setPosition(node.end_position)
		cursor.setPosition(node.position, QTextCursor.KeepAnchor)
		self.cursor = cursor
		print('expression', repr(self.main.interpreter.text[node.position:node.end_position]))
		if not re.fullmatch(format_vec3, self.main.interpreter.text[node.position:node.end_position]):
			raise EditionError("the current expression format can't be edited")
		
		for g,rdr in main.active_sceneview.stack:
			if g == obj and isinstance(rdr, PointDisplay):
				self.color = rdr.color
				rdr.position = self.position
				rdr.color = trick_color
	
	def control(self, scene, grp, subi, evt):
		''' called for mouse events started on the object 
			it can returns a callable to use as tool for the Scene
		'''
		if evt.type() == QEvent.MouseButtonPress:
			self.startpt = vec3(self.point)
			return self.move
		
	def move(self, scene, evt):
		if evt.type() == QEvent.MouseMove:
			store(self.point, scene.ptfrom((evt.x(), evt.y()), self.startpt))
			store(self.position, fvec3(self.point))
			print('at', self.position)
			scene.update()
		else:
			self.apply()
			scene.tool = None
			#if self.main.exectrigger != 0:
				#self.main.execute()
		return True
	
	def dump(self):
		''' text representation to insert in the script '''
		return 'vec3({}, {}, {})'.format(*self.point)
		
	def apply(self):
		''' update the script with the modifications '''
		pos = min(self.cursor.anchor(), self.cursor.position())
		self.cursor.beginEditBlock()
		self.cursor.removeSelectedText()
		self.cursor.insertText(self.dump())
		self.cursor.setPosition(pos, QTextCursor.KeepAnchor)
		self.cursor.endEditBlock()
	
	def finish(self):
		''' close the editor and put the view in the initial state 
			apply is called just before
		'''
		for g,rdr in scene.stack:
			if g == obj:
				rdr.position = self.position
				rdr.color = self.color

class ControledAxis(Trick):
	format = re.compile(format_axis)
	def found(self, found):
		self.axis = (vec3(), vec3())
		for j in range(2):
			for i in range(3):
				self.axis[j][i] = float(found.group(3*j+i+1))
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
