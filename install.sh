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
Darwin*)  host=macosx ;;
CYGWIN*)  host=windows ;;
MINGW*)   host=windows ;;
*)        host=unknown ;;
esac

project=$(realpath $(dirname $0))
arch=${arch:-$(arch)}
platform=${platform:-$host}
prefix=${prefix:-$project/dist/${platform}_${arch}}


case $platform in
linux)
	data=$prefix/lib/python3/dist-packages
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

# prepare directories
install -d $bin
install -d $data

# the common directories
install -d $data/themes/
install $project/uimadcad/*.py $data/
install $project/uimadcad/themes/*.qss $data/themes/
install $project/uimadcad/themes/*.yaml $data/themes/

# platform specific
case $platform in
linux)
	install $project/madcad $bin/

	install -d $prefix/share/applications/
	install $project/madcad.desktop $prefix/share/applications/
	install -d $prefix/share/icons/hicolor/scalable/apps
	install $project/uimadcad/icons/madcad-*.svg $prefix/share/icons/hicolor/scalable/apps/
	
	install -d $prefix/share/icons/hicolor/scalable/mimetypes
	install $project/mimetypes/*.svg $prefix/share/icons/hicolor/scalable/mimetypes/
	install -d $prefix/share/mime/packages/
	install $project/mimetypes/*.xml $prefix/share/mime/packages/
	;;
windows)
	install $project/madcad.bat $bin/
	
	install -d $prefix/icons
	install $project/icons/*.svg $prefix/icons/
	install $project/icons/*.ico $prefix/
	;;
?)
	echo "platform not supported: $platform"
	exit 1
	;;
esac

