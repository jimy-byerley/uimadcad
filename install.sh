#!/bin/sh
case $1 in
-h | --help)
	echo "usage:   $0 [prefix]"
	exit 0
	;;
esac

prefix=$1
if [ $prefix = '' ]; then 
	prefix=/usr/share
fi


# desktop implantation
install madcad.desktop $prefix/share/applications/
install icons/*.svg $prefix/share/icons/hicolor/scalable/apps/
install -d $prefix/share/icons/hicolor/scalable/mimetypes
install mimetypes/*.svg $prefix/share/icons/hicolor/scalable/mimetypes/
install mimetypes/*.xml $prefix/share/mime/packages/
update-mime-database ~/.local/share/mime
# shell commands
install madcad $prefix/bin/

# software files
installdir=$prefix/share/madcad
install -d $installdir
cp -r uimadcad $installdir/
# cp -r textures $installdir/
# cp -r shaders $installdir/
