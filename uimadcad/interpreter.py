from copy import deepcopy
from functools import partial
import traceback

from . import ast


class InterpreterError(Exception):	pass


class Interpreter:
	def __init__(self, filename:str):
		self.cache = {}
		self.filename = filename
		self.previous = {}
		self.ast = {}
		self.scopes = {}
		self.locations = {}
		self.usages = {}
		self.stops = []
		self.exception = None
	
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
		self.locations = ast.locate(code, self.filename)
		self.usages = ast.usage(code, self.filename)
		# ast.complete(code)
		code = ast.Module(code, type_ignores=[])
		ast.fix_locations(code)
		
		# TODO: add stop points
		
		bytecode = compile(code, self.filename, 'exec')
		module = dict(
			_madcad_global_cache = partial(ast.global_cache, self.cache),
			_madcad_copy = deepcopy,
			_madcad_scopes = self.scopes,
			_madcad_step = step,
			_madcad_vars = vars,
			)
		try:
			exec(bytecode, module, {})
		except Exception as err:
			stops = {}
			for frame, line in traceback.walk_tb(err.__traceback__):
				name = frame.f_code.co_name
				if name == '<module>':
					name = self.filename
				stops[name] = line
				# TODO: use a try finally for the scope capture
			self.usages = ast.usage(code.body, self.filename, stops=stops)
			raise
		
	def interrupt(self):
		# TODO
		pass
		
def test_interpreter():
	indev
