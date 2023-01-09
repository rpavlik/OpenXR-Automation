// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use serde::{Deserialize, Serialize};
use std::{fs, path::Path};

use crate::{
    list::{self, BasicList},
    traits::{Board, ListCollection},
    Error, GenericList, List,
};

const FORMAT: u32 = 20190412;

/// A structure representing a board as exported to JSON from Nullboard
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct BasicBoard {
    format: u32,
    id: u64,
    revision: u32,
    pub title: String,
    lists: Vec<list::BasicList>,
    history: Vec<u32>,
}

impl ListCollection for BasicBoard {
    type List = list::BasicList;

    fn named_list(&self, name: &str) -> Option<&Self::List> {
        self.lists.named_list(name)
    }

    fn named_list_mut(&mut self, name: &str) -> Option<&mut Self::List> {
        self.lists.named_list_mut(name)
    }

    fn push_list(&mut self, list: Self::List) -> &mut Self::List {
        self.lists.push_list(list)
    }
}

impl Board for BasicBoard {
    fn title(&self) -> &str {
        &self.title
    }

    fn id(&self) -> u64 {
        self.id
    }

    fn history(&self) -> &[u32] {
        self.history.as_ref()
    }

    /// Get the current revision number
    fn revision(&self) -> u32 {
        self.revision
    }

    fn format(&self) -> u32 {
        self.format
    }

    fn make_new_revision(&self) -> Self {
        let mut ret = self.clone();
        ret.increment_revision();
        ret
    }

    fn increment_revision(&mut self) {
        self.history.insert(0, self.revision);
        self.revision += 1;
    }

    fn make_new_revision_with_lists(self, lists: impl IntoIterator<Item = Self::List>) -> Self {
        let mut ret = Self {
            format: self.format,
            id: self.id,
            revision: self.revision,
            title: self.title.clone(),
            lists: lists.into_iter().map(Self::List::from).collect(),
            history: self.history,
        };
        ret.increment_revision();
        ret
    }

    fn take_lists(&mut self) -> Vec<BasicList> {
        std::mem::take(&mut self.lists)
    }
}

impl BasicBoard {
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
}

fn make_id_from_timestamp() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("could not determine time since unix epoch")
        .as_secs()
}

impl Default for BasicBoard {
    fn default() -> Self {
        Self {
            format: FORMAT,
            id: make_id_from_timestamp(),
            revision: 1,
            title: Default::default(),
            lists: Default::default(),
            history: Default::default(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GenericBoard<T> {
    format: u32,
    id: u64,
    revision: u32,
    title: String,
    lists: Vec<GenericList<T>>,
    history: Vec<u32>,
}

impl<T> GenericBoard<T> {
    /// Make a new board with a given title
    pub fn new(title: &str) -> Self {
        Self {
            title: title.to_owned(),
            ..Default::default()
        }
    }
}

impl<T> ListCollection for GenericBoard<T> {
    type List = GenericList<T>;

    fn named_list(&self, name: &str) -> Option<&Self::List> {
        self.lists.named_list(name)
    }

    fn named_list_mut(&mut self, name: &str) -> Option<&mut Self::List> {
        self.lists.named_list_mut(name)
    }

    fn push_list(&mut self, list: Self::List) -> &mut Self::List {
        self.lists.push_list(list)
    }
}

impl<T: Clone> Board for GenericBoard<T> {
    fn title(&self) -> &str {
        &self.title
    }

    fn id(&self) -> u64 {
        self.id
    }

    fn history(&self) -> &[u32] {
        self.history.as_ref()
    }

    fn revision(&self) -> u32 {
        self.revision
    }

    fn format(&self) -> u32 {
        self.format
    }

    fn make_new_revision(&self) -> Self {
        let mut ret: GenericBoard<T> = self.clone();
        ret.increment_revision();
        ret
    }
    fn increment_revision(&mut self) {
        self.history.insert(0, self.revision);
        self.revision += 1;
    }

    fn make_new_revision_with_lists(self, lists: impl IntoIterator<Item = Self::List>) -> Self {
        let mut ret = Self {
            format: self.format,
            id: self.id,
            revision: self.revision,
            title: self.title.clone(),
            lists: lists.into_iter().map(Self::List::from).collect(),
            history: self.history,
        };
        ret.increment_revision();
        ret
    }

    fn take_lists(&mut self) -> Vec<Self::List> {
        std::mem::take(&mut self.lists)
    }
}

impl<T> Default for GenericBoard<T> {
    fn default() -> Self {
        Self {
            format: FORMAT,
            id: make_id_from_timestamp(),
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
    use crate::{Board, Note};

    fn do_board_ops<T: Board>(board: T)
    where
        <<<T as ListCollection>::List as List>::Note as Note>::Data: Default,
    {
        assert_ne!(board.id(), 0);
        assert_eq!(board.format(), FORMAT);
        assert_eq!(board.revision(), 1);

        let mut next_rev = board.make_new_revision();
        assert_eq!(next_rev.revision(), 2);
        assert_eq!(next_rev.history(), vec![1]);

        assert!(next_rev.named_list("test").is_none());

        // type List =<T::List as ListCollection>::List;
        // use  <T as ListCollection>::List as MyList;

        next_rev
            .push_list_with_title("test")
            .push_note_with_data(Default::default());

        assert!(next_rev.named_list("test").is_some());

        assert_eq!(next_rev.named_list("test").unwrap().title(), "test");
        assert_eq!(next_rev.named_list("test").unwrap().notes().len(), 1);
    }
    #[test]
    fn basic_board_ops() {
        let board: BasicBoard = Default::default();
        do_board_ops(BasicBoard::default());
        do_board_ops::<GenericBoard<String>>(GenericBoard::default());
    }
}
