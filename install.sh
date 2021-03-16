#!/bin/sh

project=$(dirname $0)

# exit on error
set -eu

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
	?)
		echo "usage:  $(basename $0) [-p PREFIX] [-a ARCH] [-h PLATFORM]"
		exit 1
		;;
	esac
done

set -x

arch=${arch:-$(arch)}
platform=${platform:-linux}
prefix=${prefix:-$project/dist/${platform}_${arch}}


case $platform in
linux)
	data=$prefix/share/madcad
	bin=$prefix/bin
	;;
windows)
	data=$prefix
	bin=$prefix
	;;
?)
	echo "platform not supported: $platform"
	exit 1
	;;
esac

install -d $bin
install -d $data
# main archive
# files must be inserted in the python importation order to solve the dependency problems
$project/launcher/target/release/pack $data/uimadcad \
		uimadcad/common.py \
		uimadcad/interpreter.py \
		uimadcad/settings.py \
		uimadcad/errorview.py \
		uimadcad/detailview.py \
		uimadcad/tricks.py \
		uimadcad/sceneview.py \
		uimadcad/scriptview.py \
		uimadcad/tooling.py \
		uimadcad/gui.py \
		uimadcad/__init__.py \
		uimadcad/__main__.py

# platform specific
case $platform in
linux)
	# launcher, must be in release mode to not contain the source code
	install $project/launcher/madcad.py $bin/madcad
	install $project/launcher/target/release/liblauncher.so $data/launcher.so

	install -d $prefix/share/applications/
	install madcad.desktop $prefix/share/applications/
	install -d $prefix/share/icons/hicolor/scalable/apps
	install icons/*.svg $prefix/share/icons/hicolor/scalable/apps/
	install -d $prefix/share/icons/hicolor/scalable/mimetypes
	install mimetypes/*.svg $prefix/share/icons/hicolor/scalable/mimetypes/
	install -d $prefix/share/mime/packages/
	install mimetypes/*.xml $prefix/share/mime/packages/
	#update-mime-database ~/.local/share/mime
	;;
windows)
	# launcher, must be in release mode to not contain the source code
	install $project/launcher/madcad.py $bin/
	install $project/launcher/target/release/liblauncher.so $data/launcher.cdylib
	
	install -d $prefix/icons
	install icons/*.svg $prefix/icons/
	install icons/madcad.ico $prefix/
	;;
?)
	echo "platform not supported: $platform"
	exit 1
	;;
esac

