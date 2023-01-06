// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use serde::{Deserialize, Serialize};

use crate::{
    note::{self, map_note_text},
    traits::{self, Note},
    GenericNote,
};

/// A structure representing a list in a board as exported to JSON from Nullboard
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq, Default)]
pub struct List {
    /// Title of the list
    pub title: String,
    /// Notes in the list
    notes: Vec<note::Note>,
}

impl traits::List for List {
    type Note = note::Note;
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
}

impl List {
    /// Converts this list to a GenericList<String> by converting each Note to a GenericNote<String>
    pub fn into_generic(self) -> GenericList<String> {
        self.into()
    }
    pub fn map_notes<B>(&self, f: impl FnMut(&str) -> B) -> GenericList<B> {
        GenericList {
            title: self.title.clone(),
            notes: self.notes.iter().map(map_note_text(f)).collect(),
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

impl<T> traits::List for GenericList<T> {
    type Note = note::GenericNote<T>;

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
}

impl<T> GenericList<T> {
    /// Clone this list, transforming the notes by passing a reference to the provided function
    pub fn map_notes_as_ref<U, F: FnMut(&T) -> U>(&self, f: F) -> GenericList<U> {
        GenericList {
            title: self.title.clone(),
            notes: self.notes.iter().map(map_generic_notes_as_ref(f)).collect(),
        }
    }

    /// Map the contents of the notes in this list to create a new list
    pub fn map_note_data<B>(self, f: impl FnMut(T) -> B) -> GenericList<B> {
        GenericList {
            title: self.title,
            notes: self.notes.into_iter().map(map_generic_notes(f)).collect(),
        }
    }

    /// Filter notes using a predicate on their data
    pub fn filter_notes(self, f: impl FnMut(&T) -> bool) -> Self {
        let mut filter = filter_generic_notes(f);
        GenericList {
            title: self.title,
            notes: self.notes.into_iter().filter(&mut filter).collect(),
        }
    }

    pub fn notes_mut(&mut self) -> &mut Vec<GenericNote<T>> {
        &mut self.notes
    }

    pub fn title(&self) -> &str {
        self.title.as_ref()
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

impl From<GenericList<String>> for List {
    fn from(list: GenericList<String>) -> Self {
        Self {
            title: list.title,
            notes: list.notes.into_iter().map(note::Note::from).collect(),
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

/// Applies a function to every note in a collection of lists.
pub fn map_note_data_in_lists<'a, T, B, F: 'a + FnMut(T) -> B>(
    lists: impl IntoIterator<Item = GenericList<T>> + 'a,
    mut f: F,
) -> impl Iterator<Item = GenericList<B>> + 'a {
    // "move" moves f into the closure, &mut avoids moving it *out* of the closure in each call
    let map_list = move |list: GenericList<T>| -> GenericList<B> { list.map_note_data(&mut f) };

    lists.into_iter().map(map_list)
}

// -- filter_notes -- //

fn filter_generic_notes<T>(mut f: impl FnMut(&T) -> bool) -> impl FnMut(&GenericNote<T>) -> bool {
    move |note| f(&note.data)
}

// -- map_notes -- //

fn map_generic_notes_as_ref<T, B>(
    mut f: impl FnMut(&T) -> B,
) -> impl FnMut(&GenericNote<T>) -> GenericNote<B> {
    move |note| GenericNote {
        data: f(&note.data),
        raw: note.raw,
        min: note.min,
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
