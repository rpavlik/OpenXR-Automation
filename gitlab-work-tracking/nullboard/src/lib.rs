use serde::Deserialize;
use serde::Serialize;

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
    /// If false, we can't be confident we are interpreting this correctly.
    pub fn check_format(&self) -> bool {
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
