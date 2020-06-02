from editor import Interpreter

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
print(interpreter.execute()[0])

print('--- half ---')
print(interpreter.execute(7, backup=True)[0])

print('--- continuation ---')
print(interpreter.execute(12)[0])

print('--- insertion ---')
interpreter.change((11,1), 1, 'truc(10,12,13) or a')
print(interpreter.text())
interpreter.execute()
