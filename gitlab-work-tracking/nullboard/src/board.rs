// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use serde::{Deserialize, Serialize};
use std::{borrow::Cow, fs, path::Path};

use crate::{list::BasicList, Error, GenericList};

const FORMAT: u32 = 20190412;

/// A structure representing a board as exported to JSON from Nullboard
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct Board<'a> {
    format: u32,
    id: u64,
    revision: u32,
    pub title: String,
    lists: Vec<BasicList<'a>>,
    history: Vec<u32>,
}

impl<'a> Board<'a> {
    /// Make a new revision that replaces the lists.
    pub fn make_new_revision_with_lists(
        self,
        lists: impl IntoIterator<Item = GenericList<'a, String>>,
    ) -> Board<'a> {
        let mut ret = Self {
            format: self.format,
            id: self.id,
            revision: self.revision,
            title: self.title.clone(),
            lists: lists.into_iter().map(BasicList::from).collect(),
            history: self.history,
        };
        ret.increment_revision();
        ret
    }
}
impl Board<'_> {
    /// Make a new board with a given title
    pub fn new<'a>(title: impl Into<Cow<'a, str>>) -> Self {
        Self {
            title: title.into().into_owned(),
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

    pub fn take_lists(&mut self) -> Vec<BasicList> {
        std::mem::take(&mut self.lists)
    }
}

impl Default for Board<'_> {
    fn default() -> Self {
        Self {
            format: FORMAT,
            id: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("could not determine time since unix epoch")
                .as_secs(),
            revision: 1,
            title: Default::default(),
            lists: Default::default(),
            history: Default::default(),
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
