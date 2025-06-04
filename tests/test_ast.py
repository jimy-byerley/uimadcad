from uimadcad.ast import *


def test_parcimonize():
	from pnprint import nprint, cprint
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
	
	cprint(unparse(result))
	
	print('original', len(original_bytecode.co_code), 'parcimonized', len(bytecode.co_code))

	env = {}
	exec(bytecode, dict(
		_madcad_global_cache = partial(global_cache, cache),
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
		), env)
	nprint('cache', cache)
	assert 'b1' in cache['<input>'][ArgumentsKey(())]
	nprint('env', env)
	assert env.get('b') == 'ae'
	assert env.get('d') == ['c', 'c', 'e', 'f', 'a']
	assert env.get('s') == {'a': 'a', 'b': 'ae', 'c': 2}

def test_homogenize():
	code = parse(normalize_indent('''\
		a = 1
		if a == 1:
			b = 2
			for c in range(5):
				if c == 3:
					d = 4
					e = 3
		else:
			d = 4
		''')).body
	scope = homogenize(code)
	assert scope == {'e', 'b', 'a', 'd'}
	print(dump(Module(code, type_ignores=[]), indent=4))
	
	completion = code[1].orelse[1]
	assert isinstance(completion, Assign)
	assert completion.value.value == None
	assert set(target.id   for target in completion.targets) == {'e', 'b'}
	
	completion = code[1].body[1].body[0].orelse[0]
	assert isinstance(completion, Assign)
	assert completion.value.value == None
	assert set(target.id   for target in completion.targets) == {'e', 'd'}
	
	code = parse(normalize_indent('''\
		def f(c, *, d=None):
			a = 1
			if a == 1:
				b = 2
				if c == 3:
					d = 4
					e = 3
			else:
				d = 4
		''')).body
	scope = homogenize(code)
	assert scope == {'f'}
	print(dump(Module(code, type_ignores=[]), indent=4))
	
	completion = code[0].body[1].orelse[1]
	assert isinstance(completion, Assign)
	assert completion.value.value == None
	assert set(target.id   for target in completion.targets) == {'e', 'b'}
	
	completion = code[0].body[1].body[1].orelse[0]
	assert isinstance(completion, Assign)
	assert completion.value.value == None
	assert set(target.id   for target in completion.targets) == {'e'}

# def test_annotate():
	# indev

def test_flatten():
	from pnprint import cprint
	
	code = parse(normalize_indent('''\
		a = (b+c)+d
		'''))
	code.body = list(flatten(code.body))
	fix_missing_locations(code)
	cprint(unparse(code))
	compile(code, '<flatten>', 'exec')
	assert isinstance(code.body[-1].value, BinOp)
	assert isinstance(code.body[-1].value.left, Name)
	
	code = parse(normalize_indent('''\
		b = [5] + [i+1 for i in range(5)]
		'''))
	code.body = list(flatten(code.body))
	fix_missing_locations(code)
	cprint(unparse(code))
	compile(code, '<flatten>', 'exec')
	assert isinstance(code.body[-1].value, BinOp)
	assert isinstance(code.body[-1].value.left, Name)
	assert isinstance(code.body[-1].value.right, Name)
	
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
	fix_locations(code)
	print(dump(code, indent=4))
	compile(code, '<flatten>', 'exec')
	result = usage(code.body, '<file>')['<file>']
	nprint(result)
	assert result.ro == {'range'}
	assert result.wo == {'a'}
	assert result.rw == {'b', 'd', '_temp3', 'c', '_temp2', '_temp1', '_temp4'}
	
def test_usage_scopes():
	from pnprint import nprint
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
	nprint(usages)
	assert usages == {
        'root.truc': Usage(ro={'a', 'b'}, wo={'c'}, rw=set()),
        'root.machin': Usage(ro={'a'}, wo={'b'}, rw=set()),
        'root.chose.muche': Usage(ro={'a', 'c', 'b'}, wo={'e'}, rw={'d'}),
        'root.chose': Usage(ro=set(), wo=set(), rw=set()),
        'root': Usage(ro={'chose', 'truc', 'machin'}, wo={'t', 'c', 'm'}, rw=set()),
        }
        
	usages = usage(flatten(code.body), 'root')
	nprint(usages)
	assert usages == {
        'root.truc': Usage(ro={'a', 'b'}, wo={'_return'}, rw={'c', '_temp1'}),
        'root.machin': Usage(ro={'a'}, wo={'_return', 'b'}, rw=set()),
        'root.chose.muche': Usage(ro={'a', 'c', 'b'}, wo={'e'}, rw={'d'}),
        'root.chose': Usage(ro={'muche'}, wo={'_return'}, rw=set()),
        'root': Usage(ro={'truc', 'machin', 'chose'}, wo={'m', 'c', 't'}, rw=set()),
        }
