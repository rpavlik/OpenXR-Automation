use std::{ffi::OsString, path::Path};

use anyhow::anyhow;
use clap::Parser;
use dotenv::dotenv;
use gitlab_work::note::NoteLine;
use log::info;

#[derive(Parser, Debug)]
struct Args {
    #[arg()]
    filename: String,
}

fn parse_note(s: &str) -> Vec<NoteLine> {
    s.split("\n").map(NoteLine::parse_line).collect()
}

fn main() -> Result<(), anyhow::Error> {
    dotenv()?;
    env_logger::init();
    let args = Args::parse();

    let path = Path::new(&args.filename);

    // let out_fn = path
    //     .file_stem()
    //     .map(|p| {
    //         let mut p = p.to_owned();
    //         p.push(".updated.json");
    //         p
    //     })
    //     .ok_or_else(|| anyhow!("Could not get file stem"))?;
    // let out_path = path.with_file_name(out_fn);

    let board = nullboard_tools::Board::load_from_json(path)?;
    let notes_iter = board.lists.iter().flat_map(|list| list.notes.iter());
    for note in notes_iter {
        let lines = parse_note(&note.text);
        info!("{:?}", lines);
    }

    Ok(())
}
