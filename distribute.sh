#!/bin/sh -eu

version=$(python -c "import uimadcad; print(uimadcad.version)")
target=$(dirname $0)


while getopts "p:a:h:" arg
do
	case $arg in 
	a)
		arch=$OPTARG
		;;
	h)
		platform=$OPTARG
		;;
	p)
		format=$OPTARG
		;;
	*)
		echo "buid uimadcad and make an installation package out of it"
		echo
		echo "usage:  $(basename $0) [-p deb|tar] [-a ARCH] [-h PLATFORM]"
		exit 1
		;;
	esac
done

set -x

format=${format:-tar}
arch=${arch:-$(arch)}
platform=${platform:-linux}
prefix=$target/dist/${platform}_${arch}

# install in a dedicated folder
$target/install.sh -p $prefix -a $arch -h $platform

case $format in
tar)
	cd $(dirname $prefix)
	tar cf uimadcad-${version}-${arch}.tar.gz ${platform}-${arch}
	;;
	
zip)
	package=$target/dist/uimadcad
	rm -fr $package
	mv $prefix $package
	(
		cd $(dirname $package)
		7z a uimadcad_${version}-${arch}.zip madcad
	)
	;;
	
deb)
	# rename the tree for further additions
	package=$target/dist/deb-${arch}
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
	dpkg -b $package $target/dist/uimadcad-${version}-${arch}.deb
	;;
	
rpm)
	$target/distribute.sh -p deb -a $arch -h $platform
	# name trick for the architecture
	case $arch in
	x86_64)	debarch=amd64	;;
	*)      debarch=$arch   ;;
	esac
	
	(
		cd $target/dist
		sudo alien -r uimadcad_${version}_${debarch}.deb
		mv uimadcad-${version}-2.${arch}.rpm uimadcad-${version}.${arch}.rpm
	)
	;;
	
*)
	echo "package type not supported: $format"
	
esac
