// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use serde::{Deserialize, Serialize};
use std::{fs, io, marker::PhantomData, path::Path};

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

const FORMAT: u32 = 20190412;

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

impl List {
    pub fn into_generic(self) -> GenericList<String> {
        GenericList {
            title: self.title,
            notes: self.notes.into_iter().map(|note| note.into()).collect(),
        }
    }
}

pub struct ListsIntoGeneric<I> {
    iter: I,
}

impl<I> ListsIntoGeneric<I> {
    fn new(iter: I) -> Self {
        Self { iter }
    }
}

impl<I: Iterator<Item = List>> Iterator for ListsIntoGeneric<I> {
    type Item = GenericList<String>;

    fn next(&mut self) -> Option<Self::Item> {
        self.iter.next().map(List::into_generic)
    }
}

/// Trait to add an `into_generic()` method to the result of `Board::take_lists()`
pub trait IntoGeneric {
    type Iter;
    fn into_generic(self) -> Self::Iter;
}

impl IntoGeneric for Vec<List> {
    type Iter = ListsIntoGeneric<std::vec::IntoIter<List>>;
    fn into_generic(self) -> Self::Iter {
        ListsIntoGeneric::new(self.into_iter())
    }
}
/// Nullboard list note, with arbitrary text type
///
/// See also `Note`
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
    /// Map the "text" (data) of a note
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

/// A structure representing a list in a board as exported to JSON from Nullboard, with arbitrary note text type
///
/// See also `List`
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

/// Applies a function to every note in a collection of lists.
pub fn map_note_data_in_lists<'a, T, B, F: 'a + FnMut(T) -> B>(
    lists: impl IntoIterator<Item = GenericList<T>> + 'a,
    mut f: F,
) -> impl Iterator<Item = GenericList<B>> + 'a {
    // "move" moves f into the closure, &mut avoids moving it *out* of the closure in each call
    let map_list = move |list: GenericList<T>| -> GenericList<B> { list.map_notes(&mut f) };

    lists.into_iter().map(map_list)
}

pub struct NoteDataMap<'a, F, I> {
    iter: I,
    f: F,
    phantom: PhantomData<&'a F>,
}

impl<'a, F, I> NoteDataMap<'a, F, I> {
    pub fn new(iter: I, f: F) -> Self {
        NoteDataMap {
            iter,
            f,
            phantom: PhantomData,
        }
    }
}

impl<'a, F, I, T, B> Iterator for NoteDataMap<'a, F, I>
where
    F: 'a + FnMut(T) -> B,
    I: Iterator<Item = GenericList<T>>,
{
    type Item = GenericList<B>;

    fn next(&mut self) -> Option<Self::Item> {
        self.iter
            .next()
            .map(|list: GenericList<T>| -> GenericList<B> { list.map_notes(&mut self.f) })
    }
}

pub trait MapNoteData<'a, T, B>: 'a + Iterator<Item = GenericList<T>> {
    fn map_note_data<F: 'a + FnMut(T) -> B>(self, f: F) -> NoteDataMap<'a, F, Self>
    where
        Self: Sized,
    {
        NoteDataMap::new(self, f)
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
