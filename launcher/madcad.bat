@echo off

where python || (
	echo "python is not found in the PATH, install it in order to run that software"
	echo "it can be installed from https://www.python.org/"
	pause
	exit
)

python %0\..\madcad
