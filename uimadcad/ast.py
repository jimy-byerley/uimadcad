from __future__ import annotations
import types
from math import inf
from ast import *
from collections import Counter
from dataclasses import dataclass
from itertools import chain
from functools import partial
from copy import deepcopy

from pnprint import nprint


def parcimonize(cache: dict, scope: str, args: list, code: Iterable[AST], previous: dict) -> Iterable[AST]:
	''' make a code lazily executable by reusing as much previous results as possible '''
	assigned = Counter()
	changed = set()
	memo = dict()
	
	# new ast body
	yield from _scope_init(scope, args)
	for node in code:
		# find inputs and outputs of this statement
		deps = list(dependencies(node))
		provided = list(results(node))
		
		if not provided: 
			yield node
			continue
		
		# update the number of assignments to provided variables
		assigned.update(provided)
		# cache key for this statement
		key = '{}{}'.format(provided[0], assigned[provided[0]])
		# check if the node code or dependencies has changed
		if scope not in previous:
			previous[scope] = {}
		previous = previous[scope]
		
		if not equal(previous.get(key), node) or any(dep in changed  for dep in deps):
			# count all depending variables as changed
			changed.update(provided)
			# void cache of changed statements
			if scope in cache:
				for backups in cache[scope].values():
					backups.discard(key)
				if not cache[scope]:
					cache.pop(scope)
					
		previous[key] = deepcopy(node, memo)
		
		# functions are caching in separate scopes
		if isinstance(node, FunctionDef):
			yield _parcimonize_func(cache, scope, node, key, previous)
		
		# an expression assigned is assumed to not modify its arguments
		elif isinstance(node, Assign):
			yield from _parcimonize_assign(key, node)
		
		# an expression without result is assumed to be an inplace modification
		# a block cannot be splitted because its bodies may be executed multiple times or not at all
		elif isinstance(node, (Expr, If, For, While, Try, Match, With)):
			yield from _parcimonize_block(key, deps, node)
			
		# an expression returned is assumed to not modify its arguments
		elif isinstance(node, Return):
			yield from _parcimonize_return(key, node)
			
		# TODO: decide what to do when the target is a subscript
		
		else:
			yield node
	
def _scope_init(scope: str, args: list) -> list:
	# get the cache dictionnary for this scope
	return [Assign(
			targets = [Name('_madcad_cache', Store())],
				# all caches are coming from a global dictionnary of scope caches
			value = Call(
				Name('_madcad_global_cache', Load()),
				args = [
					Constant(scope),
					Tuple([Name(name, Load()) for name in args], Load()),
					],
				keywords = [],
				))]
				
def _parcimonize_func(
	cache: dict, 
	scope: str, 
	node: FunctionDef, 
	key: str, 
	previous: dict,
	) -> AST:
	# functions are caching in separate scopes
	subscope = scope + '.' + node.name
	# clear function caches if the function signature changed
	prev = previous.get(key)
	if not prev or node.name != prev.name or node.args != prev.args:
		cache.pop(subscope, None)
	
	args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
	if node.args.vararg:	args.append(node.args.vararg)
	if node.args.kwarg:     args.append(node.args.kwarg)
	# redefine the function with caching
	return FunctionDef(
		name = node.name,
		args = node.args,
		body = list(parcimonize(
			cache,
			# nested scope name
			scope = subscope,
			# arguments identifying the scope instance
			args = sorted([arg.arg   for arg in args]),
			code = node.body,
			previous = previous,
			)),
		decorator_list = node.decorator_list,
		)

def _parcimonize_return(key, node) -> list:
	# an expression returned is assumed to not modify its arguments
	r = _parcimonize_assign(key, Assign([Name('_return', Store())], node.value))
	r.append(Return(Name('_return', Load())))
	return r

def _parcimonize_assign(key, node) -> list:
	# an expression assigned is assumed to not modify its arguments
	return _cache_use(key, node.targets, [
		Assign(targets = [Name('_madcad_tmp', Store())], value = node.value), 
		_cache_set(key, value = Name('_madcad_tmp', Load())),
		Assign(targets = node.targets, value = Name('_madcad_tmp', Load())),
		])
		
def _parcimonize_block(key, deps, node) -> list:
	# an expression without result is assumed to be an inplace modification
	# a block cannot be splitted because its bodies may be executed multiple times or not at all
	outs = [Name(dep, Store())  for dep in deps]
	ins = [Name(dep, Load())  for dep in deps]
	return _cache_use(key, [Tuple(outs, Store())], [
		# run original code
		node,
		# cache results
		_cache_set(key, value = Tuple(ins, Load())),
		])

def _cache_use(key: hash, targets: list, generate: list) -> list:
	return [
		Assign([Name('_madcad_tmp', Store())], _cache_get(key)),
		If(
			# if cache is None
			test = Compare(
				left = Name('_madcad_tmp', Load()),
				ops = [Is()], 
				comparators = [Constant(value=None)]
				),
			# run the generating code
			body = [
				# TODO remove this debug print
					Expr(Call(Name('print', Load()), args=[Constant('generate'), Constant(key)], keywords=[])),
				] + generate,
			# retreive from cache
			orelse = [
				Assign(targets, Name('_madcad_tmp', Load())),
				# Assign(targets, Call(
				# 	func = Name('_madcad_copy', Load()),
				# 	args = [Name('_madcad_tmp', Load())],
				# 	keywords = [],
				# 	)),
				Expr(Call(Name('print', Load()), args=[Constant('cache'), Constant(key)], keywords=[])),
				],
			),
		]

def _cache_get(key) -> Expr:
	''' expression for accessing the cache value for this variable name in this function's scope '''
	return Call(
		Attribute(Name('_madcad_cache', Load()), 'get', Load()), 
		args = [Constant(key)],
		keywords = [],
		)
	
def _cache_set(key, value) -> Expr:
	''' statment for setting the given value to the given cache key '''
	return Expr(Call(
		Attribute(Name('_madcad_cache', Load()), 'set', Load()), 
		args = [Constant(key), value],
		keywords = [],
		))

def global_cache(cache: dict, scope: str, args: tuple):
	''' function retreiving/creating the caches for a function according to its arguments '''
	# maximum number of versions kept for this function
	# when inserting a new version, previous caches will be randomly poped to not get over this limit
	max_versions = 20
	
	if scope not in cache:
		cache[scope] = {}
	versions = cache[scope]
	args = ArgumentsKey(args)
	if args not in versions:
		if len(versions) > max_versions:
			versions.popitem()
		versions[args] = ScopeCache()
	return versions[args]
	
class ScopeCache:
	''' dictionnary of caches for a scope 
	
		this class simply provide convenient methods including deepcopy when necessary
	'''
	def __init__(self):
		self.scope = {}
	
	# list of types that do not need to be deepcopied (immutable or uncopiable)
	whitelist = {types.ModuleType, types.FunctionType, type, str, int, float}
	
	def get(self, key):
		''' retreive a cached value '''
		cached = self.scope.get(key)
		if not type(cached) in self.whitelist:
			try:
				cached = deepcopy(cached)
			except TypeError:
				pass
		return cached
	
	def set(self, key, value):
		''' cache a value '''
		if not type(value) in self.whitelist:
			try:
				value = deepcopy(value)	
			except TypeError:
				pass
		self.scope[key] = value
		
	def discard(self, key):
		''' discard a cached value, if any '''
		self.scope.pop(key, None)
		
	def __bool__(self):
		return bool(self.scopes)
		
	def __contains__(self, key):
		return key in self.scope
	
class ArgumentsKey:
	__slots__ = 'key', 'args'
	def __init__(self, args):
		self.key = 0
		for arg in args:
			try:	
				id = hash(arg)
			except TypeError:  
				id = 0
			self.key ^= id
		self.args = args
	def __hash__(self):
		return self.key
	def __eq__(self, other):
		return self.args == other.args
	def __repr__(self):
		return '{}({})'.format(self.__class__.__name__, ', '.join(repr(arg) for arg in self.args))
	
def test_parcimonize():
	from pnprint import nprint
	from dis import dis
	from copy import deepcopy
	
	filename = '<input>'
	code = normalize_indent('''\
		from math import sin, cos

		def foo():
			a = 'a'
			return a
		def bar(x, y):
			return x+y
		def boo(x):
			return [x]
		def fah(first, *args):
			first.extend(args)

		e, f = 'e', 'f'
		a = foo()
		c = 'c'
		{}
		d = boo(c)
		fah(d, c, e, f, foo())
		s = dict(a=a, b=b, c=1)
		s['c'] = 2

		if True: pass
		g = 0 if False else 1
		''')
	
	original_ast = parse(code.format('b = bar(a, c)'))
	original_bytecode = compile(original_ast, filename, 'exec')
	cache = {}
	previous = {}
	
	result = Module(
		list(parcimonize(cache=cache, scope=filename, args=(), code=original_ast.body, previous=previous)),
		type_ignores=[])
	nprint('\n'.join(dump(node) for node in result.body))
	fix_missing_locations(result)
	bytecode = compile(result, filename, 'exec')
	dis(bytecode)
	print('original', len(original_bytecode.co_code), 'parcimonized', len(bytecode.co_code))

	env = {}
	exec(bytecode, dict(
		_madcad_global_cache = partial(global_cache, cache),
		_madcad_copy = deepcopy,
		), env)
	nprint('env', env)
	nprint('cache', cache)
	assert env.get('b') == 'ac'
	assert env.get('d') == ['c', 'c', 'e', 'f', 'a']
	assert env.get('s') == {'a': 'a', 'b': 'ac', 'c': 2}

	second_ast = parse(code.format('b = bar(a, e)'))
	result = Module(
		list(parcimonize(cache=cache, scope=filename, args=(), code=second_ast.body, previous=previous)),
		type_ignores=[])
	fix_missing_locations(result)
	bytecode = compile(result, filename, 'exec')
	nprint('cache', cache)
	assert 'b1' not in cache['<input>'][ArgumentsKey(())]
	env = {}
	exec(bytecode, dict(
		_madcad_global_cache = partial(global_cache, cache),
		_madcad_copy = deepcopy,
		), env)
	nprint('cache', cache)
	assert 'b1' in cache['<input>'][ArgumentsKey(())]
	nprint('env', env)
	assert env.get('b') == 'ae'
	assert env.get('d') == ['c', 'c', 'e', 'f', 'a']
	assert env.get('s') == {'a': 'a', 'b': 'ae', 'c': 2}

def dependencies(node: AST) -> iter:
	''' yield names of variables a node depends on '''
	if isinstance(node, Name) and isinstance(node.ctx, Load):
		yield node.id
	elif isinstance(node, FunctionDef):
		for expr in chain(node.args.defaults, node.args.kw_defaults):
			yield from dependencies(expr)
	else:
		for child in iter_child_nodes(node):
			yield from dependencies(child)

def results(node: AST, inplace=False) -> iter:
	''' yield names of variables assigned by a node '''
	if isinstance(node, Name) and (isinstance(node.ctx, Store) or inplace):
		yield node.id
	elif isinstance(node, (FunctionDef, ClassDef)):
		yield node.name
	elif isinstance(node, (Import, ImportFrom)):
		for alias in node.names:
			yield alias.name
	elif isinstance(node, Return):
		yield 'return'
	elif isinstance(node, Assign):
		for target in node.targets:
			yield from results(target, inplace=True)
	elif isinstance(node, (Attribute, Subscript)):
		yield from results(node.value, inplace)
	elif isinstance(node, Call):
		if isinstance(node.func, Attribute):
			# nprint(node.func, list(results(node.func.value, inplace=True)))
			yield from results(node.func.value, inplace=True)
		arg = next(iter(node.args), None) or next(iter(node.keywords), None)
		if arg:
			yield from results(arg, inplace=True)
	else:
		for child in iter_child_nodes(node):
			yield from results(child)

def annotate(tree: AST, text: str):
	''' enrich nodes by useful informations, such as start-end text position of tokens
		currently
			* position
			* end_position
	'''	
	# assigne a text position to each node
	currentloc = (1,0)
	currentpos = 0
	for node in walk(tree):
		if hasattr(node, 'lineno'):
			target = _loc(node)
			node.position = _advancepos(text, target, currentpos, currentloc)
			currentloc = target
			currentpos = node.position
	
	
	# find the end of each node
	def recursive(node):
		# process subnodes first
		propagate(node, recursive)
		
		# node specific length calculation
		if isinstance(node, Name):
			node.end_position = node.position + len(node.id)
		if isinstance(node, keyword):
			node.position, node.end_position = node.value.position, node.value.end_position
		elif isinstance(node, (Num, Str, Constant)):
			i = node.position
			if isinstance(node, Constant) and isinstance(node.value, str) or isinstance(node, Str):
				marker = text[i]
				if text[i:i+3] == 3*marker:
					marker = 3*marker
				node.end_position = text.find(marker, i+len(marker)) + len(marker)
			elif isinstance(node, Constant) and node.value in {None, True, False}:
				node.end_position = node.position + len(str(node.value))
			else:
				while i < len(text) and text[i] in '0123456789+-e.rufbx':	i+=1
				node.end_position = i
		
		# generic retreival from the last child
		elif hasattr(node, 'position'):
			if not hasattr(node, 'end_position'):
				node.end_position = node.position
			for child in iter_child_nodes(node):
				if hasattr(child, 'end_position'):
					node.end_position = max(node.end_position, child.end_position)
		
		if isinstance(node, Attribute):
			i = node.end_position + len(node.attr)
			while i < len(text) and text[i].isalnum():	i+=1
			node.end_position = i
		elif isinstance(node, (Subscript, List, ListComp)):
			node.end_position = text.find(']', node.end_position)+1
		elif isinstance(node, (Dict, Set, DictComp, SetComp)):
			node.end_position = text.find('}', node.end_position)+1
		elif isinstance(node, (expr, Tuple)) and not isinstance(node, (Constant, Num)):
			start = node.position
			if not isinstance(node, (Call, Tuple)):
				start -= 1
				while start > 0 and text[start] in ' \t\n':	start -= 1
				if start >= 0 and text[start] != '(':
					return
			end = node.end_position
			if end < len(text) and text[end] == '(':	end += 1
			while end < len(text) and text[end] in ' \t\n,':	end += 1
			if end >= len(text) or text[end] != ')':
				return
			node.position = start
			node.end_position = end+1
		elif isinstance(node, alias) and node.name == '*':
			node.end_position = node.position + len(node.name)
	
	recursive(tree)
	
def test_annotate():
	indev

# default interesting expressions to flatten
flatten_selection = {Call, BoolOp, BinOp, Tuple, List, Return, ListComp, DictComp}

def flatten(code: Iterable[AST], filter=None, vars:set=None) -> list:
	''' unroll all expressions and assign temporary values to hidden variables
	
		inplace node modifications
		
		yield the new sequence of instruction
	'''
	if vars is None:
		vars = set()
	if filter is None:
		filter = lambda node: type(node) in flatten_selection
	
	# choose temporary names
	def tempname():
		i = 0
		while True:
			i += 1
			name = '_temp'+str(i)
			if name not in vars:
				vars.add(name)
				return name
				
	allowed = {Call, BoolOp, BinOp, Tuple, List, Attribute, Subscript}
	
	def capture(node: AST):
		# an expression not already captured at a lower level has to be captured with a temporary name
		if isinstance(node, expr):
			if type(node) in allowed:
				propagate(node, capture)
			if filter(node):
				name = tempname()
				captured.append(Assign([Name(name, Store())], node))
				return Name(name, Load())
		# return values get a special name
		elif isinstance(node, Return):
			if type(node.value) in allowed:
				propagate(node.value, capture)
			if filter(node.value):
				captured.append(Assign([Name('_return', Store())], node.value))
				return Return(Name('_return', Load()))
		# assignemnts are already named so no need for capture again
		elif isinstance(node, Assign):
			if type(node.value) in allowed:
				propagate(node.value, capture)
		elif isinstance(node, keyword):
			capture(node.value)
		
		# in a block, captures should create variables inside the block
		elif isinstance(node, (Module, FunctionDef, For, While, With)):
			node.body = list(flatten(node.body, filter))
		elif isinstance(node, If):
			node.body = list(flatten(node.body, filter, vars=vars))
			node.orelse = list(flatten(node.orelse, filter, vars=vars))
		elif isinstance(node, Match):
			node.subject = capture(node.subject)
			node.cases = [list(flatten(child, filter, vars=vars))  for child in node.cases]
	
	captured = []
	for node in code:
		# process statement
		capture(node)
		# add captured values juste before statement
		yield from captured
		yield node
		captured.clear()
		
def test_flatten():
	code = parse(normalize_indent('''\
		a = (b+c)+d
		'''))
	code.body = list(flatten(code.body))
	nprint(dump(code))
	fix_missing_locations(code)
	compile(code, '<flatten>', 'exec')
	assert isinstance(code.body[-1].value, BinOp)
	assert isinstance(code.body[-1].value.left, Name)
	
	code = parse(normalize_indent('''\
		b = [5] + [i+1 for i in range(5)]
		'''))
	code.body = list(flatten(code.body))
	nprint(dump(code))
	fix_missing_locations(code)
	compile(code, '<flatten>', 'exec')
	assert isinstance(code.body[-1].value, BinOp)
	assert isinstance(code.body[-1].value.left, Name)
	assert isinstance(code.body[-1].value.right, Name)
	
def steppize(code:list[AST], scope:str) -> Iterator[AST]:
	def filter(node):
		if isinstance(node, (Module, FunctionDef)):
			node.body = list(steppize(node.body, scope+'.'+node.name))
		elif isinstance(node, expr):
			pass
		else:
			propagate(node, filter)
	
	l = len(code)
	for i, node in enumerate(code):
		propagate(node, filter)
		yield node
		yield Expr(Call(
			func = Name('_madcad_step', Load()),
			args = [Constant(scope), Constant(i), Constant(l)],
			keywords = [],
			))

def report(code:list[AST], scope:str) -> list[AST]:
	''' change the given code to report its variables to madcad '''
	def filter(node):
		if isinstance(node, (Module, FunctionDef)):
			node.body = report(node.body, scope+'.'+node.name)
		else:
			propagate(node, filter)
	
	for node in code:
		filter(node)
	
	return [Try(body=code, handlers=[], orelse=[], finalbody=[
		Assign(
			targets = [Subscript(Name('_madcad_scopes', Load()), Constant(scope), Store())],
			value = Call(Name('_madcad_vars', Load()), args=[], keywords=[]),
			),
		# Expr(Call(Name('print', Load()), args=[
		# 	Constant('report'), Constant(scope), 
		# 	# Call(Name('_madcad_vars', Load()), args=[], keywords=[]),
		# 	], keywords=[])),
		])]

def locate(code:Iterable[AST], scope:str, locations=None) -> dict[str, dict[str, AST]]:
	''' change the given code to report its variables to madcad '''
	if locations is None:
		locations = {}
	locations[scope] = {}
	def filter(node):
		if isinstance(node, (Module, FunctionDef)):
			locations[scope][node.name] = node
			locate(node.body, scope+'.'+node.name, locations)
		elif isinstance(node, Assign):
			for target in node.targets:
				if isinstance(target, Name):
					locations[scope][target.id] = node
		else:
			propagate(node, filter)
	
	for node in code:
		filter(node)
	
	return locations
	
def test_locate():
	def check(located, reference):
		for scope, vars in reference.items():
			assert scope in located
			for name, ty in vars.items():
				assert name in located[scope]
				assert isinstance(located[scope][name], ty)
	
	code = parse(normalize_indent('''\
		def truc(a, b):
			c = a+b+1
			return c+1		
		def machin(a):
			b = a+1
			return a+2
		def chose(a, b):
			def muche(c):
				d = a+b
				e = d+c
				return e
			return muche(1)
		
		t = truc(2,3)
		m = machin(1)
		c = chose(2,3)
		''')).body
	located = locate(code, 'root')
	check(located, {
        'root': {
                'truc': FunctionDef,
                'machin': FunctionDef,
                'chose': FunctionDef,
                't': Assign,
                'm': Assign,
                'c': Assign,
                },
        'root.truc': {'c': Assign},
        'root.machin': {'b': Assign},
        'root.chose': {'muche': FunctionDef},
        'root.chose.muche': {'d': Assign, 'e': Assign},
        })
	
	code = flatten(code)
	located = locate(code, 'root')
	check(located, {
        'root': {
                'truc': FunctionDef,
                'machin': FunctionDef,
                'chose': FunctionDef,
                't': Assign,
                'm': Assign,
                'c': Assign,
                },
        'root.truc': {
			'c': Assign,
			'_temp1': Assign,
			'_return': Assign,
			},
        'root.machin': {'b': Assign},
        'root.chose': {
			'muche': FunctionDef,
			'_return': Assign,
			},
        'root.chose.muche': {'d': Assign, 'e': Assign},
        })

	
def usage(code:list, scope:str, usages:dict=None, stops:dict=None) -> dict[str, Usage]:
	''' analyse the variables usage in all function scopes defined in this AST 
		
		Args:
			usages: dictionnary of scopes usages, updated and returned by this function, leaving it empty creates a new dict
			stops:  dictionnary of stop points in each scope, useful to know the scope's variables usage before an exception
	'''
	if usages is None:	usages = {}
	if stops is None:	stops = {}
	
	ro = set()  # only read
	wo = set() # only written
	rw = set()  # read and written

	def filter(node):
		if isinstance(node, (Module, FunctionDef)):
			usage(node.body, scope+'.'+node.name, usages, stops)
		# if the current node is after the current scope's end, do not count its usages
		elif getattr(node, 'lineno', 0) > stops.get(scope, inf):
			pass
		# count statement usages
		elif isinstance(node, (Expr, Assign)):
			for var in dependencies(node):
				if var in wo or var in rw:
					rw.add(var)
				else:
					ro.add(var)
				wo.discard(var)
			for var in results(node):
				ro.discard(var)
				rw.discard(var)
				wo.add(var)
		else:
			propagate(node, filter)
	
	for node in code:
		filter(node)
	
	usages[scope] = Usage(ro, wo, rw)
	return usages

@dataclass(slots=True)
class Usage:
	ro: set
	''' variables that were always read but never written in the current scope '''
	wo: set
	''' variables that were lastly wrote but never read in the current scope '''
	rw: set
	''' variables that were wrote then read in the current scope '''

def test_usage():
	from pnprint import nprint
	code = parse(normalize_indent('''\
		a = (b+c)+d
		b = [5] + [i+1 for i in range(5)]
		if 1 != 0:
			c = 1 + 2
		else:
			d = 1 + 3 + 4
		'''))
	code.body = list(flatten(code.body))
	fix_missing_locations(code)
	nprint(dump(code))
	compile(code, '<flatten>', 'exec')
	ro, wo, rw = usage(code)
	nprint(ro, wo, rw)
	assert ro == {'range'}
	assert wo == {'a'}
	assert rw == {'b', 'd', '_temp3', 'c', '_temp2', 'i', '_temp1'}
	
def test_usage_scopes():
	code = parse(normalize_indent('''\
		def truc(a, b):
			c = a+b+1
			return c+1		
		def machin(a):
			b = a+1
			return a+2
		def chose(a, b):
			def muche(c):
				d = a+b
				e = d+c
				return e
			return muche(1)
		
		t = truc(2,3)
		m = machin(1)
		c = chose(2,3)
		'''))

	usages = usage(code.body, 'root')
	assert usages == {
        'root.truc': Usage(ro={'a', 'b'}, wo={'c'}, rw=set()),
        'root.machin': Usage(ro={'a'}, wo={'b'}, rw=set()),
        'root.chose.muche': Usage(ro={'a', 'c', 'b'}, wo={'e'}, rw={'d'}),
        'root.chose': Usage(ro=set(), wo=set(), rw=set()),
        'root': Usage(ro={'chose', 'truc', 'machin'}, wo={'t', 'c', 'm'}, rw=set()),
        }
        
	usages = usage(flatten(code.body), 'root')
	assert usages == {
        'root.truc': Usage(ro={'a', 'b'}, wo={'_return'}, rw={'c'}),
        'root.machin': Usage(ro={'a'}, wo={'_return', 'b'}, rw=set()),
        'root.chose.muche': Usage(ro={'a', 'c', 'b'}, wo={'e'}, rw={'d'}),
        'root.chose': Usage(ro={'muche'}, wo={'_return'}, rw=set()),
        'root': Usage(ro={'truc', 'machin', 'chose'}, wo={'m', 'c', 't'}, rw=set()),
        }

	
def fix_locations(node: AST):
	''' set approximative line and column locations to AST nodes that are missing these 
		(generally they are procedurally created nodes) 
	'''
	for child in iter_child_nodes(node):
		fix_locations(child)
		# values from childs
		if lineno := getattr(child, 'lineno', 0):
			node.lineno = min(getattr(node, 'lineno', lineno), lineno)
		if col_offset := getattr(child, 'col_offset', 0):
			node.col_offset = min(getattr(node, 'col_offset', col_offset), col_offset)
	# default values
	node.lineno = getattr(node, 'lineno', 0)
	node.col_offset = getattr(node, 'col_offset', 0)

def equal(a: AST, b: AST) -> bool:
	''' check that the operations performed by node a are equivalent to operations performed by node b '''
	if type(a) != type(b):	return False
	
	if isinstance(a, Name):
		return a.id == b.id
	elif isinstance(a, alias):
		return a.name == b.name and (a.asname or a.name) == (b.asname or b.name)
	elif isinstance(a, Constant):
		return a.value == b.value
	elif isinstance(a, Attribute):
		if a.attr != b.attr:	return False
	elif isinstance(a, (FunctionDef, AsyncFunctionDef, ClassDef)):
		if a.name != b.name:	return False
	elif isinstance(a, ImportFrom):
		if a.module != b.module:   return False
	elif isinstance(a, (Global, Nonlocal)):
		if set(a.names) != set(b.names):	return False
	
	for ca, cb in zip(iter_child_nodes(a), iter_child_nodes(b)):
		if not equal(ca, cb):
			return False
	return True

def propagate(node: AST, process: callable):
	''' apply process to node's children 
		if process returns something not None, it's used to inplace replace the child in the node
	'''
	for fieldname,value in iter_fields(node):
		if isinstance(value, AST):
			child = value
			replacement = process(child)
			if replacement:
				setattr(node, fieldname, replacement)
		elif isinstance(value, list):
			for i,child in enumerate(value):
				replacement = process(child)
				if replacement:
					value[i] = replacement


def normalize_indent(text):
	''' remove the indentation level of the first line from all lines '''
	indent = None
	for i,c in enumerate(text):
		if not c.isspace():
			indent = text[:i]
			break
	if indent:
		return text[len(indent):].replace('\n'+indent, '\n')
	elif indent is not None:
		return text
	else:
		return ''

def _advancepos(text, loc, startpos=0, startloc=(1,0), tab=1):
	''' much like textpos but starts from a point (with startpos and startloc) and can advance forward or backward '''
	i = startpos
	l,c = startloc
	while l < loc[0]:	
		i = text.find('\n', i)+1
		l += 1
	while l > loc[0]:
		i = text.rfind('\n', 0, i)
		l -= 1
	i = text.rfind('\n', 0, i)+1
	i += loc[1]
	return i

def _loc(node):
	''' text location of an AST node '''
	return (node.lineno, node.col_offset)

def textpos(text, loc, tab=1):
	''' string index of the given text location (line,column) '''
	i = 0
	l, c = 1, 0
	while l < loc[0]:	
		i = text.find('\n', i)+1
		l += 1
	while c < loc[1]:
		if text[i] == '\t':	c += tab
		else:				c += 1
		i += 1
	return i
