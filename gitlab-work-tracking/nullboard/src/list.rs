// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::borrow::Cow;

use serde::{Deserialize, Serialize};

use crate::{
    note::{map_note_data_string, BasicNote},
    GenericNote, List, Note,
};

/// A structure representing a list in a board as exported to JSON from Nullboard
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq, Default)]
pub struct BasicList {
    /// Title of the list
    pub title: String,
    /// Notes in the list
    notes: Vec<BasicNote>,
}

impl BasicList {
    pub fn new<'a>(title: impl Into<Cow<'a, str>>, notes: Vec<BasicNote>) -> Self {
        Self {
            title: title.into().into_owned(),
            notes,
        }
    }
}
impl List for BasicList {
    type Note = BasicNote;
    type NoteData = String;

    fn title(&self) -> &str {
        &self.title
    }

    fn notes(&self) -> &[Self::Note] {
        &self.notes
    }

    fn notes_mut(&mut self) -> &mut Vec<Self::Note> {
        &mut self.notes
    }

    fn filter_notes<F: FnMut(&Self::NoteData) -> bool>(self, mut f: F) -> Self {
        Self {
            title: self.title,
            notes: self.notes.into_iter().filter(|n| f(n.data())).collect(),
        }
    }
    fn map_note_data<B, F: FnMut(Self::NoteData) -> B>(self, f: F) -> GenericList<B> {
        GenericList {
            title: self.title.clone(),
            notes: self
                .notes
                .into_iter()
                .map(map_note_data_string(f))
                .collect(),
        }
    }
}

/// A structure representing a list in a board as exported to JSON from Nullboard, with arbitrary note text type
///
/// See also `List`
#[derive(Clone, PartialEq, Eq, Default)]
pub struct GenericList<T> {
    /// Title of the list
    title: String,
    /// Notes in the list
    notes: Vec<GenericNote<T>>,
}

impl<T> GenericList<T> {
    pub fn new<'a>(title: impl Into<Cow<'a, str>>, notes: Vec<GenericNote<T>>) -> Self {
        Self {
            title: title.into().into_owned(),
            notes,
        }
    }
}

fn map_generic_notes<T, B>(
    mut f: impl FnMut(T) -> B,
) -> impl FnMut(GenericNote<T>) -> GenericNote<B> {
    move |note| GenericNote {
        data: f(note.data),
        raw: note.raw,
        min: note.min,
    }
}

impl<T> List for GenericList<T> {
    type Note = GenericNote<T>;

    type NoteData = T;

    fn title(&self) -> &str {
        &self.title
    }

    fn notes(&self) -> &[Self::Note] {
        &self.notes
    }

    fn notes_mut(&mut self) -> &mut Vec<Self::Note> {
        &mut self.notes
    }

    fn filter_notes<F: FnMut(&Self::NoteData) -> bool>(self, mut f: F) -> Self {
        Self {
            title: self.title,
            notes: self.notes.into_iter().filter(|n| f(n.data())).collect(),
        }
    }

    fn map_note_data<B, F: FnMut(Self::NoteData) -> B>(self, f: F) -> GenericList<B> {
        GenericList {
            title: self.title.clone(),
            notes: self.notes.into_iter().map(map_generic_notes(f)).collect(),
        }
    }
}

impl<T: core::fmt::Debug> core::fmt::Debug for GenericList<T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("GenericList")
            .field("title", &self.title)
            .field("notes", &self.notes)
            .finish()
    }
}

impl From<GenericList<String>> for BasicList {
    fn from(list: GenericList<String>) -> Self {
        Self {
            title: list.title,
            notes: list.notes.into_iter().map(BasicNote::from).collect(),
        }
    }
}

impl From<BasicList> for GenericList<String> {
    fn from(list: BasicList) -> Self {
        Self {
            title: list.title,
            notes: list.notes.into_iter().map(GenericNote::from).collect(),
        }
    }
}

/// Applies a function to every note in a collection of lists.
pub fn map_note_data_in_lists<'a, T, B, F: 'a + FnMut(T) -> B>(
    lists: impl IntoIterator<Item = GenericList<T>> + 'a,
    mut f: F,
) -> impl Iterator<Item = GenericList<B>> + 'a {
    // "move" moves f into the closure, &mut avoids moving it *out* of the closure in each call
    let map_list = move |list: GenericList<T>| -> GenericList<B> { list.map_note_data(&mut f) };

    lists.into_iter().map(map_list)
}
