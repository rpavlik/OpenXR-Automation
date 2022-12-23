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
