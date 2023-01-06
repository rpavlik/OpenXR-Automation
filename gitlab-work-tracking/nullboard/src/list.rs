// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::borrow::Cow;

use serde::{Deserialize, Serialize};

use crate::{note::BasicNote, GenericNote, List, Note, NoteIteratorAdapters};

/// A structure representing a list in a board as exported to JSON from Nullboard
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq, Default)]
pub struct BasicList<'a> {
    /// Title of the list
    title: Cow<'a, str>,
    /// Notes in the list
    notes: Vec<BasicNote>,
}

impl<'a> BasicList<'a> {
    pub fn new(title: impl Into<Cow<'a, str>>, notes: Vec<BasicNote>) -> Self {
        Self {
            title: title.into(),
            notes,
        }
    }
}
impl List for BasicList<'_> {
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
    fn map_note_data<'a, B, F: FnMut(Self::NoteData) -> B>(self, f: F) -> GenericList<'a, B> {
        GenericList {
            title: self.title.clone(),
            notes: self.notes.into_iter().map_note_data(f).collect(),
        }
    }
}

/// A structure representing a list in a board as exported to JSON from Nullboard, with arbitrary note text type
///
/// See also `List`
#[derive(Clone, PartialEq, Eq, Default)]
pub struct GenericList<'a, T> {
    /// Title of the list
    title: Cow<'a, str>,
    /// Notes in the list
    notes: Vec<GenericNote<T>>,
}

impl<'a, T> GenericList<'a, T> {
    pub fn new(title: impl Into<Cow<'a, str>>, notes: Vec<GenericNote<T>>) -> Self {
        Self {
            title: title.into(),
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

impl<'a, T> List for GenericList<'a, T> {
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

    fn map_note_data<'de, B, F: FnMut(Self::NoteData) -> B>(self, f: F) -> GenericList<'de, B> {
        GenericList {
            title: self.title,
            notes: self.notes.into_iter().map(map_generic_notes(f)).collect(),
        }
    }
}

impl<T: core::fmt::Debug> core::fmt::Debug for GenericList<'_, T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("GenericList")
            .field("title", &self.title)
            .field("notes", &self.notes)
            .finish()
    }
}

impl<'a> From<GenericList<'a, String>> for BasicList<'a> {
    fn from(list: GenericList<String>) -> Self {
        Self {
            title: list.title,
            notes: list.notes.into_iter().map(BasicNote::from).collect(),
        }
    }
}

impl<'a> From<BasicList<'a>> for GenericList<'a, String> {
    fn from(list: BasicList) -> Self {
        Self {
            title: list.title,
            notes: list.notes.into_iter().map(GenericNote::from).collect(),
        }
    }
}

/// Applies a function to every note in a collection of lists.
pub fn map_note_data_in_lists<'a, T, B, F: 'a + FnMut(T) -> B>(
    lists: impl IntoIterator<Item = GenericList<'a, T>> + 'a,
    mut f: F,
) -> impl Iterator<Item = GenericList<'a, B>> + 'a {
    // "move" moves f into the closure, &mut avoids moving it *out* of the closure in each call
    let map_list = move |list: GenericList<T>| -> GenericList<B> { list.map_note_data(&mut f) };

    lists.into_iter().map(map_list)
}
