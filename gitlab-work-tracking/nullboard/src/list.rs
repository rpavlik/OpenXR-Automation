// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use serde::{Deserialize, Serialize};

use crate::{note::map_note_text, GenericNote, Note};

/// A structure representing a list in a board as exported to JSON from Nullboard
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq, Default)]
pub struct List {
    /// Title of the list
    pub title: String,
    /// Notes in the list
    pub notes: Vec<Note>,
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

/// Applies a function to every note in a collection of lists.
pub fn map_note_data_in_lists<'a, T, B, F: 'a + FnMut(T) -> B>(
    lists: impl IntoIterator<Item = GenericList<T>> + 'a,
    mut f: F,
) -> impl Iterator<Item = GenericList<B>> + 'a {
    // "move" moves f into the closure, &mut avoids moving it *out* of the closure in each call
    let map_list = move |list: GenericList<T>| -> GenericList<B> { list.map_notes(&mut f) };

    lists.into_iter().map(map_list)
}

/// Iterator over lists with their note data mapped/transformed
pub struct ListsNoteDataMap<F, I> {
    iter: I,
    f: F,
}

impl<F, I> ListsNoteDataMap<F, I> {
    pub fn new(iter: I, f: F) -> Self {
        ListsNoteDataMap { iter, f }
    }
}

impl<F, I, T, B> Iterator for ListsNoteDataMap<F, I>
where
    F: FnMut(T) -> B,
    I: Iterator<Item = GenericList<T>> + Sized,
{
    type Item = GenericList<B>;

    fn next(&mut self) -> Option<Self::Item> {
        self.iter.next().map(|list| list.map_notes(&mut self.f))
    }
}

/// Trait to add `map_note_data` method to iterators over lists and map their note data
pub trait ListsMapNoteData<T>: Sized {
    fn map_note_data<B, F: FnMut(T) -> B>(self, f: F) -> ListsNoteDataMap<F, Self>;
}
impl<T, U> ListsMapNoteData<T> for U
where
    U: Iterator<Item = GenericList<T>>,
{
    fn map_note_data<B, F: FnMut(T) -> B>(self, f: F) -> ListsNoteDataMap<F, Self>
    where
        Self: Sized,
    {
        ListsNoteDataMap::new(self, f)
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
