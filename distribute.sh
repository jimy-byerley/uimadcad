#!/bin/sh -eux

version=0.5
target=$(dirname $0)


while getopts "a:h:" arg
do
	case $arg in 
	a)
		arch=$OPTARG
		;;
	h)
		platform=$OPTARG
		;;
	?)
		echo "usage:  $(basename $0) (deb|tar) [-a ARCH] [-h PLATFORM]"
		exit 1
		;;
	esac
done

set -x

format=$1
arch=${arch:-$(arch)}
platform=${platform:-linux}
prefix=$target/dist/${platform}_${arch}

# install in a dedicated folder
$target/install.sh -p $prefix -a $arch -h $platform

case $format in
tar)
	cd $(dirname $prefix)
	tar cf madcad_${version}_${arch}.tar.gz ${platform}_${arch}
	;;
	
deb)
	# rename the tree for further additions
	package=$target/dist/deb_${arch}
	rm -fr $package
	install -d $package
	mv $prefix $package/usr
	
	# name trick for the architecture
	case $arch in
	x86_64)	arch=amd64	;;
	esac
	
	# write manifest
	cp -r $target/DEBIAN $package/
	export VERSION=$version ARCH=$arch
	envsubst < $target/DEBIAN/control > $package/DEBIAN/control
	
	# write md5 sums
	(
		cd $package
		find . -type f \
			! -regex '.*.hg.*' ! -regex '.*?debian-binary.*' ! -regex '.*?DEBIAN.*' \
			-printf '%P ' | xargs md5sum > DEBIAN/md5sums
	)
	
	# create package
	dpkg -b $package $target/dist/madcad_${version}_${arch}.deb
	;;
	
?)
	echo "package type not supported: $format"
	
esac
