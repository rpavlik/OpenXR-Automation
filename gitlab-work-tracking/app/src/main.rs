use std::{ffi::OsString, path::Path};

use anyhow::anyhow;
use clap::Parser;

#[derive(Parser, Debug)]
struct Args {
    #[arg()]
    filename: String,
}

fn main() -> Result<(), anyhow::Error> {
    env_logger::init();
    let args = Args::parse();
    let path = Path::new(&args.filename);
    let out_fn = path
        .file_stem()
        .map(|p| {
            let mut p = p.to_owned();
            p.push(".updated.json");
            p
        })
        .ok_or_else(|| anyhow!("Could not get file stem"))?;
    let out_path = path.with_file_name(out_fn);
    let board = nullboard_tools::Board::load_from_json(path)?;
    Ok(())
}
