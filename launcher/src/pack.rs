use std::error::Error;
use std::io::{Read, Write};
use std::fs::File;
use std::env;
use std::path::Path;
use zip::ZipWriter;
use cryptostream::write;
use openssl::symm::Cipher;
use base64::{decode, encode};
use rand::prelude::*;

fn main() -> Result<(), Box<dyn Error>> {
	let key: Vec<_> = decode("kjtbxCPw3XPFThb3mKmzfg==")?;
	let iv: Vec<_> = decode("dB0Ej+7zWZWTS5JUCldWMg==")?;
	
	let mut args = env::args();
	args.next().unwrap();
	let arpath = args.next() .expect("expected a first argument for the archive name");
	let files = args;
	
	// open src zip archive
	//println!("write {}", arpath);
	let mut archive = ZipWriter::new(
			File::create(Path::new(&arpath)) .expect("unable to write the output archive")
			);
	
	// archive files in the given order
	let mut buff = [0u8; 1024];
	for filepath in files {
		if ! Path::new(&filepath).is_file() {
			println!("  ignore {}", filepath);
			continue;
		}
		// open the source file
		//println!("  read {}", filepath);
		let mut file = File::open(Path::new(&filepath)) .expect("cannot find the given input file");
		// start the encrypted file
		archive.start_file(
				Path::new(&filepath) .file_stem().unwrap() .to_str().unwrap(),
				zip::write::FileOptions::default()
					.compression_method(zip::CompressionMethod::Stored)	// no compression, as encrypted there is nothing to gain
				) .expect("cannot create file in the output archive");
		
		// encrypt file
		let mut encryptor = write::Encryptor::new(
								&mut archive, 
								Cipher::aes_128_cbc(), 
								&key, 
								&iv
								)?;
		loop {
			let count = file.read(&mut buff) .expect("read failure from input file");
			if count == 0	{ break; }
			encryptor.write(&buff[0 .. count]) .expect("write failure to output file");
		}
	}
	
	Ok(())
}
