from __future__ import annotations

from copy import deepcopy
from functools import partial
from dataclasses import dataclass
from bisect import bisect_right
import traceback

from . import ast


class InterpreterError(Exception):	pass


class Interpreter:
	''' this class execute the uimadcad file code and exposes the resulting scope, errors and code analysis 
	
		Since the code might not have changed much between two executions, executing the code actually performs a lot of caching and reexecute only the changed portions of code and the code that depends on it
	'''
	filename: str
	source: str
	ast: AST
	scopes: dict[str, dict[str, object]]
	definitions: dict[str, dict[str, AST]]
	locations: list[Located]
	identified: dict[int, Located]
	usages: dict[str, Usage]
	exception: Exception
	
	def __init__(self, filename:str):
		self.cache = {}
		self.filename = filename
		self.source = ''
		self.previous = {}
		self.ast = {}
		self.scopes = {}
		self.identified = {}
		self.definitions = {}
		self.locations = []
		self.usages = {}
		# TODO reimplement interpreter early stop
		# self.stops = []
		self.exception = None
	
	def execute(self, source:str, step:callable):
		''' execute the code in the given string
		
			- this is a lazy execution where all previous result from previous execution are reused when possible
			- step is a callback executed regularly during execuction:
				
				step(scope: str, current_line: int, total_lines: int)
		'''
		# nprint('cache', self.cache)
		
		self.exception = None
		self.source = source
		
		try:
			code = self.ast = ast.parse(source).body
			# collect user variable with their original definitions, the definition will be modified inplace but at least we have its root
			originals = ast.locate(code, self.filename)
			self.usages = ast.usage(code, self.filename)
			code = list(ast.parcimonize(self.cache, self.filename, (), code, self.previous, 
				# assuming only calls might be long ioperations
				filter=lambda node: any(isinstance(node, ast.Call)  for node in ast.walk(node)),
				))
			code = list(ast.steppize(code, self.filename, 
				# place steps before parcimonized steps because assumed to be long operations
				filter=lambda node: isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == '_madcad_tmp',
				))
			code = list(ast.flatten(code))
			# collect temporary variables created by this interpreter
			created = ast.locate(code, self.filename)
			code = list(ast.report(code, self.filename, clear=False))
			
			# prefer original defintions to created ones
			self.definitions = {
				scope: created[scope] | originals[scope]
				for scope in originals
				}
			
			# TODO: add stop points
			
			# build a sorted location index
			locations = []
			for scope, definitions in self.definitions.items():
				for name, node in definitions.items():
					if haslocation(node):
						located = node
					elif isinstance(node, ast.Assign) and haslocation(node.value):
						located = node.value
					else:
						continue
					locations.append(Located(
						node,
						# range(node.position, node.end_position), 
						# TODO: optimize this position search
						range(
							ast.textpos(source, (located.lineno, located.col_offset)), 
							ast.textpos(source, (located.end_lineno, located.end_col_offset)),
							),
						scope, 
						name,
						))
			self.locations = sorted(locations, key=lambda item: item.range.start)
			
			code = ast.Module(list(code), type_ignores=[])
			ast.fix_locations(code)
			bytecode = compile(code, self.filename, 'exec')
			module = dict(
				_madcad_global_cache = partial(ast.global_cache, self.cache),
				_madcad_scopes = self.scopes,
				_madcad_step = step,
				_madcad_vars = vars,
				)
			
			# from pnprint import cprint
			# print(ast.dump(code, indent=4))
			# cprint(ast.unparse(code))
		
			try:
				exec(bytecode, module, module)
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
			
			self.identified = {
				id(self.scopes[located.scope][located.name]): located  
				for located in self.locations
				if located.scope in self.scopes
				and located.name in self.scopes[located.scope]}
				
		except Exception as err:
			self.exception = err
			
	def names_crossing(self, area:range) -> Iterator[Located]:
		''' yield variables with text range crossing the given position range '''
		stop = bisect_right(self.locations, area.stop, key=lambda item: item.range.start)
		for i in reversed(range(0, stop)):
			item = self.locations[i]
			if item.range.start in area or item.range.stop in area:
				yield item
			else:
				break
					
	def name_at(self, position:int) -> Located:
		''' find the variable with the smallest text range enclosing the given position '''
		stop = bisect_right(self.locations, position, key=lambda item: item.range.start)
		for i in reversed(range(0, stop)):
			item = self.locations[i]
			if position in item.range:
				return item
		raise IndexError('no node at the given position')
	
	def scope_at(self, position:int) -> Located:
		''' find the scope with the smallest text range enclosing the given position '''
		stop = bisect_right(self.locations, position, key=lambda item: item.range.start)
		for i in reversed(range(0, stop)):
			item = self.locations[i]
			if position in item.range and isinstance(item.node, ast.FunctionDef):
				return item.scope+'.'+item.name
		return self.filename
	
	def interrupt(self):
		# TODO
		pass

@dataclass
class Located:
	node: AST
	range: range
	scope: str
	name: str

	
def haslocation(node):
	return ( 
		getattr(node, 'lineno', 0) and getattr(node, 'end_lineno', 0) 
		and getattr(node, 'col_offset', 0) and getattr(node, 'end_col_offset', 0) 
		)
		
def test_interpreter():
	# TODO test that the interpreter result is the same as the normal python interpreter even when reexecuting and modifying parts of the script
	indev
