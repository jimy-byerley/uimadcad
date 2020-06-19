from editor_ast import *
from nprint import nprint

interpreter = Interpreter('''
a = 1
b = 2
# definition statement
def truc(a, b, c):
	print(a,b,c)
	return 1
# composed expressions
truc(a,b,a+b)
# composed expresions splitted across lines
truc(
	a,
	b,
	(
		a+b
	))
''')

print('--- full ---')
interpreter.execute()
nprint(interpreter.current)
nprint(interpreter.locations)

print('--- half ---')
interpreter.execute(textpos(interpreter.text, (8,0)))
nprint(interpreter.current)
nprint(interpreter.locations)

print('--- continuation ---')
interpreter.execute(-1)
nprint(interpreter.current)
nprint(interpreter.locations)

print('--- insertion ---')
interpreter.change(textpos(interpreter.text, (12,1)), 1, 'truc(10,12,13) or a')
print(interpreter.text)
interpreter.execute()
nprint(interpreter.current)
nprint(interpreter.locations)
