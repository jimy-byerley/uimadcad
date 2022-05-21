#!/bin/sh -eu

while getopts "p:a:h:" arg; do
	case $arg in 
	a)
		arch=$OPTARG
		;;
	h)
		platform=$OPTARG
		;;
	p)
		prefix=$OPTARG
		;;
	*)
		echo "build uimadcad and install it at the specified prefix path"
		echo
		echo "usage:  $(basename $0) [-p PREFIX] [-a ARCH] [-h PLATFORM]"
		exit 1
		;;
	esac
done

set -x

case $(uname -s) in
Linux*)	  host=linux ;;
Darwin*)  host=mac ;;
CYGWIN*)  host=windows ;;
MINGW*)   host=windows ;;
*)        host=unknown ;;
esac

project=$(realpath $(dirname $0))
arch=${arch:-$(arch)}
platform=${platform:-$host}
prefix=${prefix:-$project/dist/${platform}_${arch}}
release=release 
# NOTE launcher must be in release mode to not contain the source code


case $platform in
linux)
	data=$prefix/share/madcad
	bin=$prefix/bin
	binformat=
	cargotarget=$arch-unknown-linux-gnu
	;;
windows)
	data=$prefix
	bin=$prefix
	binformat=.exe
	cargotarget=$arch-pc-windows-msvc
	export PATH=/c/Strawberry/perl/bin:$PATH
	;;
?)
	echo "platform not supported: $platform"
	exit 1
	;;
esac


# compile the launcher
if [ "$(arch)" = "$arch" ] && [ "$platform" = "$host" ] 
then	cargotarget=
fi

(
	cd launcher
	cargo build --release

	if [ -n "$cargotarget" ]
	then
		export PYO3_CROSS_PYTHON_VERSION=3.9
		export PYO3_CROSS_INCLUDE_DIR="$project/../cross/python-$PYO3_CROSS_PYTHON_VERSION-$arch/include"
		export PYO3_CROSS_LIB_DIR="$project/../cross/python-$PYO3_CROSS_PYTHON_VERSION-$arch/lib"
		#$project/../cross/setup.sh $PYO3_CROSS_PYTHON_VERSION $arch
		
		cargo build --release --target $cargotarget
	fi
)

# prepare directories
install -d $bin
install -d $data
# main archive
# files must be inserted in the python importation order to solve the dependency problems
$project/launcher/target/release/pack$binformat $data/uimadcad \
		uimadcad/__init__.py \
		uimadcad/common.py \
		uimadcad/apputils.py \
		uimadcad/interpreter.py \
		uimadcad/settings.py \
		uimadcad/errorview.py \
		uimadcad/detailview.py \
		uimadcad/tricks.py \
		uimadcad/sceneview.py \
		uimadcad/scriptview.py \
		uimadcad/tooling.py \
		uimadcad/gui.py \
		uimadcad/__main__.py

# the main executable
install $project/launcher/uimadcad.py $bin/madcad
	
# platform specific
case $platform in
linux)
	# NOTE launcher, must be in release mode to not contain the source code
	install $project/launcher/target/$cargotarget/$release/liblauncher.so $data/launcher.so

	install -d $prefix/share/applications/
	install $project/madcad.desktop $prefix/share/applications/
	install -d $prefix/share/icons/hicolor/scalable/apps
	install $project/icons/*.svg $prefix/share/icons/hicolor/scalable/apps/
	install -d $prefix/share/icons/hicolor/scalable/mimetypes
	install $project/mimetypes/*.svg $prefix/share/icons/hicolor/scalable/mimetypes/
	install -d $prefix/share/mime/packages/
	install $project/mimetypes/*.xml $prefix/share/mime/packages/
	#update-mime-database ~/.local/share/mime
	;;
windows)
	install $project/launcher/madcad.bat $bin/
	install $project/launcher/target/$cargotarget/$release/launcher.dll $data/launcher.pyd
	
	install -d $prefix/icons/breeze
	python minimal-theme.py $project/icons/list.txt $project/breeze $prefix/icons/breeze
 	install $project/icons/*.svg $prefix/icons/breeze/actions/symbolic/
	install $project/icons/madcad.ico $prefix/
	;;
?)
	echo "platform not supported: $platform"
	exit 1
	;;
esac

