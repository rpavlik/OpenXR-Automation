// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Rylie Pavlik <rylie.pavlik@collabora.com>

use std::borrow::Cow;

use serde::{Deserialize, Serialize};

use crate::{note::BasicNote, GenericNote, List, Note, NoteIteratorAdapters};

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
    type NoteType = BasicNote;

    fn from_title(title: &str) -> Self {
        Self {
            title: title.to_owned(),
            notes: Default::default(),
        }
    }

    fn title(&self) -> &str {
        &self.title
    }

    fn notes(&self) -> &[Self::NoteType] {
        &self.notes
    }

    fn notes_mut(&mut self) -> &mut Vec<Self::NoteType> {
        &mut self.notes
    }

    fn filter_notes<F: FnMut(&<Self::NoteType as Note>::Data) -> bool>(self, f: F) -> Self {
        let mut f = f;
        Self {
            title: self.title,
            notes: self.notes.into_iter().filter(|n| f(n.data())).collect(),
        }
    }

    fn map_note_data<B, F: FnMut(<Self::NoteType as Note>::Data) -> B>(
        self,
        f: F,
    ) -> GenericList<B> {
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
    type NoteType = GenericNote<T>;

    fn from_title(title: &str) -> Self {
        Self {
            title: title.to_owned(),
            notes: Default::default(),
        }
    }

    fn title(&self) -> &str {
        &self.title
    }

    fn notes(&self) -> &[Self::NoteType] {
        &self.notes
    }

    fn notes_mut(&mut self) -> &mut Vec<Self::NoteType> {
        &mut self.notes
    }
    fn filter_notes<F: FnMut(&<Self::NoteType as Note>::Data) -> bool>(self, mut f: F) -> Self {
        Self {
            title: self.title,
            notes: self.notes.into_iter().filter(|n| f(n.data())).collect(),
        }
    }

    fn map_note_data<B, F: FnMut(<Self::NoteType as Note>::Data) -> B>(
        self,
        f: F,
    ) -> GenericList<B> {
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
