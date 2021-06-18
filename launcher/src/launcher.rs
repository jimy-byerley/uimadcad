use std::error::Error;
use std::io::Read;
use std::fs::File;
use std::path::Path;
use zip::ZipArchive;
use cryptostream::read;
use openssl::symm::Cipher;
use base64::decode;
use pyo3::prelude::*;
use pyo3::wrap_pyfunction;
use pyo3::exceptions::PyOSError;


#[pymodule]
fn launcher(_py: Python, m: &PyModule) -> PyResult<()> {
	m.add_function(wrap_pyfunction!(run, m)?)?;
	Ok(())
}

#[pyfunction]
fn run(path: &str) -> PyResult<()> {
	match run_archive(Path::new(path)) {
		Ok(()) => Ok(()),
		Err(e) => Err(
			if e.is::<PyErr>() {
				*e.downcast::<PyErr>().unwrap()
			}
			else {
				PyOSError::new_err(format!("{:?}", e))
			}),
	}
}

fn run_archive(path: &Path) -> Result<(), Box<dyn Error>> {
	let key: Vec<_> = decode("kjtbxCPw3XPFThb3mKmzfg==")?;
	let iv: Vec<_> = decode("dB0Ej+7zWZWTS5JUCldWMg==")?;
	
	// open src zip archive
	let mut archive = ZipArchive::new(
			File::open(path) .expect("main archive not found")
			) .expect("unable to read main archive");
	
	// create the main module
	let module = path.file_stem() .expect("bad name format for archive") 
						.to_str() .unwrap();
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
		let file = archive.by_index(i)?;
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
					) ?;
		package.dict().set_item("__package__", module)?;
		// register the new sub module
		package.dict().set_item(&name, sub)?;
	}
	
	println!("run python");
	py.run(&main, None, None)?;

	Ok(())
}
