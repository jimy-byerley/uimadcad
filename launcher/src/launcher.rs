use std::error::Error;
use std::io::Read;
use std::fs::File;
use std::path::Path;
use zip::ZipArchive;
use cryptostream::read;
use openssl::symm::Cipher;
use base64::decode;
use pyo3::prelude::*;

fn main() -> Result<(), Box<dyn Error>> {
	let key: Vec<_> = decode("kjtbxCPw3XPFThb3mKmzfg==")?;
	let iv: Vec<_> = decode("dB0Ej+7zWZWTS5JUCldWMg==")?;
	let module = "uimadcad";
	
	// select the archive path
	let mut path = std::env::current_exe()?.to_owned();
	path.pop();
	path.push(module);
	if ! path.exists()  {
		path.pop();
		path.pop();
		path.push("share");
		path.push("madcad");
		path.push(module);
	}
	
	// open src zip archive
	let mut archive = ZipArchive::new(
			File::open(Path::new(&path)) .expect("main archive not found")
			) .expect("unable to read main archive");
	
	// create the main module
	let gil = Python::acquire_gil();
	let py = gil.python();
	let package = PyModule::new(py, module)?;
	package.dict() .set_item("__package__", module)?;
	let sys = py.import("sys")?;
	sys.dict() .get_item("modules").unwrap() .set_item(module, package)?;
	
	let mut main = String::new();
	
	// load submodules in the archiving order
	for i in 0..archive.len() {
		// source data file
		let mut file = archive.by_index(i)?;
		let name = file.name().to_owned();

		// decrypt file
		let mut decryptor = read::Decryptor::new(
								file, 
								Cipher::aes_128_cbc(), 
								&key, 
								&iv
								)?;
		let mut code = String::new();
		decryptor.read_to_string(&mut code) .expect("unable to extract");
		
		// capture main
		if name == "__main__"	{ main = code.clone(); }
		
		// load module
		let sub = PyModule::from_code(py, 
					&code, 
					&format!("{}/{}.py", module, name), 
					&format!("{}.{}", module, name)
					) .expect(&name);
		package.dict().set_item("__package__", module)?;
		// register the new sub module
		package.dict().set_item(&name, sub)?;
	}
	
	println!("run python");
	py.run(&main, None, None) .ok();	// if python stop on an exception, it's still ok
	
	Ok(())
}
