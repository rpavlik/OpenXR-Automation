use std::fs;
use std::io;
use std::path::Path;

use serde::Deserialize;
use serde::Serialize;

#[derive(thiserror::Error, Debug)]
pub enum Error {
    #[error("IO error")]
    IoError(#[from] io::Error),

    #[error("Format mismatch")]
    FormatMismatch,

    #[error("JSON parsing error")]
    JsonParseError(#[from] serde_json::Error),
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
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
    pub lists: Vec<List>,
    history: Vec<u32>,
}

const FORMAT: u32 = 20190412;

impl Board {
    /// Make a new board with a given title
    pub fn new(title: &str) -> Self {
        let mut ret: Self = Default::default();
        ret.title = title.to_owned();
        ret
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

    pub fn get_revision(&self) -> u32 {
        self.revision
    }

    pub fn make_new_revision_with_lists(&self, lists: Vec<GenericList<String>>) -> Self {
        let mut ret = Self {
            format: self.format,
            id: self.id,
            revision: self.revision,
            title: self.title.clone(),
            lists: lists.into_iter().map(|l| List::from(l)).collect(),
            history: self.history.clone(),
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

impl Default for Note {
    fn default() -> Self {
        Self {
            text: Default::default(),
            raw: false,
            min: false,
        }
    }
}

/// Nullboard list note, with arbitrary text type
#[derive(Debug)]
pub struct GenericNote<T>
where
    T: core::fmt::Debug,
{
    /// Contents of the note
    pub text: T,
    /// Whether the note is shown "raw" (without a border, makes it look like a sub-header)
    pub raw: bool,
    /// Whether the note is shown minimized/collapsed
    pub min: bool,
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

impl<T: std::fmt::Debug> GenericNote<T> {
    // pub fn new_from_text_and_note_flags(text: T, old_note: &Note) -> Self {
    //     GenericNote {
    //         text,
    //         raw: old_note.raw,
    //         min: old_note.min,
    //     }
    // }

    pub fn with_replacement_text<U: std::fmt::Debug>(&self, text: U) -> GenericNote<U> {
        GenericNote {
            text,
            raw: self.raw,
            min: self.min,
        }
    }
}

impl Note {
    pub fn with_replacement_text<T: std::fmt::Debug>(&self, text: T) -> GenericNote<T> {
        GenericNote {
            text,
            raw: self.raw,
            min: self.min,
        }
    }

    pub fn map_text<T: std::fmt::Debug, F: Fn(&str) -> T>(&self, f: F) -> GenericNote<T> {
        self.with_replacement_text(f(&self.text))
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

/// A structure representing a list in a board as exported to JSON from Nullboard, with arbitrary note text type
#[derive(Debug)]
pub struct GenericList<T: core::fmt::Debug> {
    /// Title of the list
    pub title: String,
    /// Notes in the list
    pub notes: Vec<GenericNote<T>>,
}

impl From<GenericList<String>> for List {
    fn from(list: GenericList<String>) -> Self {
        Self {
            title: list.title,
            notes: list.notes.into_iter().map(|n| Note::from(n)).collect(),
        }
    }
}

impl From<List> for GenericList<String> {
    fn from(list: List) -> Self {
        Self {
            title: list.title,
            notes: list
                .notes
                .into_iter()
                .map(|n| GenericNote::from(n))
                .collect(),
        }
    }
}

// -- map_note_text --//

fn map_generic_note_text<T: std::fmt::Debug, B: std::fmt::Debug>(
    mut f: impl FnMut(&T) -> B,
) -> impl FnMut(&GenericNote<T>) -> GenericNote<B> {
    move |note| GenericNote {
        text: f(&note.text),
        raw: note.raw,
        min: note.min,
    }
}
impl<T: core::fmt::Debug> GenericList<T> {
    pub fn map_note_text<U: std::fmt::Debug, F: FnMut(&T) -> U>(&self, f: F) -> GenericList<U> {
        // let mut f = f;
        GenericList {
            title: self.title.clone(),
            notes: self
                .notes
                .iter()
                // .map(move |note| note.map_text(f))
                .map(map_generic_note_text(f))
                .collect(),
        }
    }
}

fn map_note_text<B: std::fmt::Debug>(
    mut f: impl FnMut(&str) -> B,
) -> impl FnMut(&Note) -> GenericNote<B> {
    move |note| GenericNote {
        text: f(&note.text),
        raw: note.raw,
        min: note.min,
    }
}

impl List {
    pub fn map_note_text<T: std::fmt::Debug, F: FnMut(&str) -> T>(&self, f: F) -> GenericList<T> {
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

// fn map_generic_list<T: std::fmt::Debug, B: std::fmt::Debug>(
//     mut f: impl FnMut(&GenericList<T>) -> GenericList<B>,
// ) -> impl FnMut(&GenericList<T>) -> GenericList<B> {
//     // let mut map_note = ;
//     let f_ref = &f;
//     |list| list.map_note_text(f_ref)
//     // GenericList {
//     //     title: list.title.clone(),
//     //     // notes: list.notes.iter().map(map_generic_note_text(f)).collect(),
//     //     notes: list.map_note_text(f)
//     // }
// }

/// A structure representing the lists in a board, with arbitrary note type
#[derive(Debug, Default)]
pub struct GenericLists<T: core::fmt::Debug>(pub Vec<GenericList<T>>);

impl<T: core::fmt::Debug> GenericLists<T> {
    pub fn new() -> Self {
        Self(Default::default())
    }
}

impl From<GenericLists<String>> for Vec<List> {
    fn from(lists: GenericLists<String>) -> Self {
        lists.0.into_iter().map(|l| List::from(l)).collect()
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
