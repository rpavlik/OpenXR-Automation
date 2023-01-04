// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use serde::{Deserialize, Serialize};
use std::{fs, io, path::Path};

pub mod experiment;

#[derive(thiserror::Error, Debug)]
pub enum Error {
    #[error("IO error")]
    IoError(#[from] io::Error),

    #[error("Format mismatch")]
    FormatMismatch,

    #[error("JSON parsing error")]
    JsonParseError(#[from] serde_json::Error),
}

/// A single "note" or "card" in a Nullboard-compatible format
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq, Default)]
pub struct Note {
    /// Contents of the note
    pub text: String,
    /// Whether the note is shown "raw" (without a border, makes it look like a sub-header)
    pub raw: bool,
    /// Whether the note is shown minimized/collapsed
    pub min: bool,
}

/// A structure representing a list in a board as exported to JSON from Nullboard
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq, Default)]
pub struct List {
    /// Title of the list
    pub title: String,
    /// Notes in the list
    pub notes: Vec<Note>,
}

/// A structure representing a board as exported to JSON from Nullboard
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct Board {
    format: u32,
    id: u64,
    revision: u32,
    pub title: String,
    lists: Vec<List>,
    history: Vec<u32>,
}

const FORMAT: u32 = 20190412;

impl Board {
    /// Make a new board with a given title
    pub fn new(title: &str) -> Self {
        Self {
            title: title.to_owned(),
            ..Default::default()
        }
    }

    /// Load a board from a JSON file
    pub fn load_from_json(filename: &Path) -> Result<Self, Error> {
        let contents = fs::read_to_string(filename)?;
        let parsed: Self = serde_json::from_str(&contents)?;
        if !parsed.check_format() {
            return Err(Error::FormatMismatch);
        }
        Ok(parsed)
    }

    /// Serialize to a pretty-printed JSON file
    pub fn save_to_json(&self, filename: &Path) -> Result<(), Error> {
        let contents = serde_json::to_string_pretty(self)?;
        fs::write(filename, contents)?;
        Ok(())
    }

    /// If false, we can't be confident we are interpreting this correctly.
    fn check_format(&self) -> bool {
        self.format == FORMAT
    }

    /// Increment the revision number, and place the old one on the history list.
    pub fn increment_revision(&mut self) {
        self.history.insert(0, self.revision);
        self.revision += 1;
    }

    /// Return a clone of this board, with an updated revision number and history.
    pub fn make_new_revision(&self) -> Self {
        let mut ret = self.clone();
        ret.increment_revision();
        ret
    }

    /// Get the current revision number
    pub fn get_revision(&self) -> u32 {
        self.revision
    }

    pub fn take_lists(&mut self) -> Vec<List> {
        std::mem::take(&mut self.lists)
    }

    /// Make a new revision that replaces the lists.
    pub fn make_new_revision_with_lists(
        self,
        lists: impl IntoIterator<Item = GenericList<String>>,
    ) -> Self {
        let mut ret = Self {
            format: self.format,
            id: self.id,
            revision: self.revision,
            title: self.title.clone(),
            lists: lists.into_iter().map(List::from).collect(),
            history: self.history,
        };
        ret.increment_revision();
        ret
    }
}

impl Default for Board {
    fn default() -> Self {
        Self {
            format: FORMAT,
            id: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            revision: 1,
            title: Default::default(),
            lists: Default::default(),
            history: Default::default(),
        }
    }
}
impl Note {
    pub fn new(contents: &str) -> Self {
        Self {
            text: contents.to_owned(),
            raw: false,
            min: false,
        }
    }
}

/// Nullboard list note, with arbitrary text type
pub struct GenericNote<T> {
    /// Contents of the note
    pub text: T,
    /// Whether the note is shown "raw" (without a border, makes it look like a sub-header)
    pub raw: bool,
    /// Whether the note is shown minimized/collapsed
    pub min: bool,
}

impl<T: core::fmt::Debug> core::fmt::Debug for GenericNote<T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("GenericNote")
            .field("text", &self.text)
            .field("raw", &self.raw)
            .field("min", &self.min)
            .finish()
    }
}

impl From<GenericNote<String>> for Note {
    fn from(note: GenericNote<String>) -> Self {
        Self {
            text: note.text,
            raw: note.raw,
            min: note.min,
        }
    }
}

impl<T> GenericNote<T> {
    pub fn with_replacement_text<U>(&self, text: U) -> GenericNote<U> {
        GenericNote {
            text,
            raw: self.raw,
            min: self.min,
        }
    }
    pub fn map<B>(self, f: impl FnOnce(T) -> B) -> GenericNote<B> {
        let text = f(self.text);

        GenericNote {
            text,
            raw: self.raw,
            min: self.min,
        }
    }
}

impl Note {
    pub fn with_replacement_text<T>(&self, text: T) -> GenericNote<T> {
        GenericNote {
            text,
            raw: self.raw,
            min: self.min,
        }
    }

    pub fn map_text<T, F: Fn(&str) -> T>(&self, f: F) -> GenericNote<T> {
        self.with_replacement_text(f(&self.text))
    }

    pub fn map<B, F: Fn(String) -> B>(self, f: F) -> GenericNote<B> {
        let text = f(self.text);

        GenericNote {
            text,
            raw: self.raw,
            min: self.min,
        }
    }
}

impl From<Note> for GenericNote<String> {
    fn from(note: Note) -> Self {
        Self {
            text: note.text,
            raw: note.raw,
            min: note.min,
        }
    }
}

// impl<T> GenericNote<T> {
//     pub fn map<B>(self, f: &mut impl FnMut(T) -> B) -> GenericNote<B> {
//         let text = f(self.text);

//         GenericNote {
//             text,
//             raw: self.raw,
//             min: self.min,
//         }
//     }
// }

/// A structure representing a list in a board as exported to JSON from Nullboard, with arbitrary note text type
pub struct GenericList<T> {
    /// Title of the list
    pub title: String,
    /// Notes in the list
    pub notes: Vec<GenericNote<T>>,
}

impl<T: core::fmt::Debug> core::fmt::Debug for GenericList<T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("GenericList")
            .field("title", &self.title)
            .field("notes", &self.notes)
            .finish()
    }
}
// fn map_generic_note<T, B>(
//     f: &mut impl FnMut(T) -> B,
// ) -> impl FnMut(GenericNote<T>) -> GenericNote<B> + '_ {
//     // let f = &mut f;
//     move |note| note.map(f)
// }

// impl<T> GenericList<T> {
//     pub fn map<B>(self, f: &mut impl FnMut(T) -> B) -> GenericList<B> {
//         GenericList {
//             title: self.title,
//             notes: self.notes.into_iter().map(map_generic_note(f)).collect(),
//         }
//     }
// }

impl From<GenericList<String>> for List {
    fn from(list: GenericList<String>) -> Self {
        Self {
            title: list.title,
            notes: list.notes.into_iter().map(Note::from).collect(),
        }
    }
}

impl From<List> for GenericList<String> {
    fn from(list: List) -> Self {
        Self {
            title: list.title,
            notes: list.notes.into_iter().map(GenericNote::from).collect(),
        }
    }
}

// -- map_note_text --//

fn map_generic_note_text_as_ref<T, B>(
    mut f: impl FnMut(&T) -> B,
) -> impl FnMut(&GenericNote<T>) -> GenericNote<B> {
    move |note| GenericNote {
        text: f(&note.text),
        raw: note.raw,
        min: note.min,
    }
}

fn map_generic_note_text<T, B>(
    mut f: impl FnMut(T) -> B,
) -> impl FnMut(GenericNote<T>) -> GenericNote<B> {
    move |note| GenericNote {
        text: f(note.text),
        raw: note.raw,
        min: note.min,
    }
}

impl<T> GenericList<T> {
    pub fn map_note_text_as_ref<U, F: FnMut(&T) -> U>(&self, f: F) -> GenericList<U> {
        // let mut f = f;
        GenericList {
            title: self.title.clone(),
            notes: self
                .notes
                .iter()
                // .map(move |note| note.map_text(f))
                .map(map_generic_note_text_as_ref(f))
                .collect(),
        }
    }

    pub fn map_notes<B>(self, f: impl FnMut(T) -> B) -> GenericList<B> {
        GenericList {
            title: self.title,
            notes: self
                .notes
                .into_iter()
                .map(map_generic_note_text(f))
                .collect(),
        }
    }
}

fn map_note_text<B>(mut f: impl FnMut(&str) -> B) -> impl FnMut(&Note) -> GenericNote<B> {
    move |note| GenericNote {
        text: f(&note.text),
        raw: note.raw,
        min: note.min,
    }
}

impl List {
    pub fn map_notes<B>(&self, f: impl FnMut(&str) -> B) -> GenericList<B> {
        // let mut f = f;
        GenericList {
            title: self.title.clone(),
            notes: self
                .notes
                .iter()
                // .map(move |note| note.map_text(f))
                .map(map_note_text(f))
                .collect(),
        }
    }
}

/// A structure representing the lists in a board, with arbitrary note type
#[derive(Default)]
pub struct GenericLists<T>(pub Vec<GenericList<T>>);

impl<T> GenericLists<T> {
    pub fn new() -> Self {
        Self(Default::default())
    }
}

impl From<GenericLists<String>> for Vec<List> {
    fn from(lists: GenericLists<String>) -> Self {
        lists.0.into_iter().map(List::from).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn basic_board_ops() {
        let board: Board = Default::default();
        assert_ne!(board.id, 0);
        assert_eq!(board.format, FORMAT);
        assert_eq!(board.revision, 1);

        let next_rev = board.make_new_revision();
        assert_eq!(next_rev.revision, 2);
        assert_eq!(next_rev.history, vec![1]);
    }
}
