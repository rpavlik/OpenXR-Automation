// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::io;

#[derive(thiserror::Error, Debug)]
pub enum Error {
    #[error("IO error")]
    IoError(#[from] io::Error),

    #[error("Format mismatch")]
    FormatMismatch,

    #[error("JSON parsing error")]
    JsonParseError(#[from] serde_json::Error),
}

pub mod board;
pub mod iterators;
pub mod list;
pub mod note;
pub mod traits;

pub use board::GenericBoard;
pub use iterators::{ListIteratorAdapters, NoteIteratorAdapters};
pub use list::GenericList;
pub use note::GenericNote;
pub use traits::{Board, List, ListCollection, Note};
