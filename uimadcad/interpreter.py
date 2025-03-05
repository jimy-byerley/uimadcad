from copy import deepcopy
from functools import partial

from . import ast


class InterpreterError(Exception):	pass


class Interpreter:
	def __init__(self, filename:str):
		self.cache = {}
		self.filename = filename
		self.previous = {}
		self.ast = {}
		self.vars = {}
		self.scopes = {}
		self.stops = []
		self.exception = None
		self.wo = set()
		self.ro = set()
		self.rw = set()
		
		# TODO: remove these debug values
		# import madcad
		# self.scopes[filename] = {
		# 	'cube': madcad.brick(width=madcad.vec3(1)),
		# 	'base': madcad.mat4(),
		# 	}
	
	def execute(self, source:str, step:callable):
		''' execute the code in the given string
		
			- this is a lazy execution where all previous result from previous execution are reused when possible
			- step is a callback executed regularly during execuction:
				
				step(scope: str, current_line: int, total_lines: int)
		'''
		from pnprint import nprint
		nprint(self.cache)
		
		code = self.ast = ast.parse(source)
		ast.annotate(code, source)
		code = list(ast.parcimonize(self.cache, self.filename, (), code.body, self.previous))
		code = list(ast.flatten(code))
		code = list(ast.steppize(code, self.filename))
		code = ast.report(code, self.filename)
		self.vars = ast.locate(code, self.filename)
		# ast.complete(code)
		code = ast.Module(code, type_ignores=[])
		ast.fix_missing_locations(code)
		
		# nprint(ast.dump(code))
		nprint(self.cache)
		
		# TODO: add stop points
		
		bytecode = compile(code, self.filename, 'exec')
		module = dict(
			_madcad_global_cache = partial(ast.global_cache, self.cache),
			_madcad_copy = deepcopy,
			_madcad_scopes = self.scopes,
			_madcad_step = step,
			_madcad_vars = vars,
			)
		exec(bytecode, module, {})
		
	def interrupt(self):
		# TODO
		pass
		
def test_interpreter():
	indev
