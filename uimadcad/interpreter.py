from copy import deepcopy
import .ast


class InterpreterError(Exception):	pass


class Interpreter:
	def __init__(self, filename:str):
		self.cache = {}
		self.filename = filename
		self.previous = {}
		self.ast = {}
		self.vars = {}
		self.scopes = {}
		
	def execute(self, code:str, step:callable):
		self.ast = ast.parse(code)
		code = ast.annotate(code)
		code = ast.parcimonize(cache, self.filename, (), code, self.previous)
		code = ast.flatten(code)
		code = ast.steppize(code)
		code = ast.report(code)
		code = ast.Module(code, type_ignores=[])
		complete(code)
		self.vars = ast.locate(code)
		
		bytecode = compile(code, self.filename, 'exec')
		module = dict(
			_madcad_global_cache = partial(ast.global_cache, self.cache),
			_madcad_copy = deepcopy,
			_madcad_scopes = self.scopes,
			_madcad_step = step,
			_madcad_vars = vars,
			)
		exec(bytecode, module, {})
		
def test_interpreter():
	indev
