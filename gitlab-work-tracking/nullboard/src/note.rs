// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use serde::{Deserialize, Serialize};

/// Iterator over mapping/transforming note data iterating over notes.
pub struct NoteDataMap<F, I> {
    iter: I,
    f: F,
}

impl<F, I> NoteDataMap<F, I> {
    pub fn new(iter: I, f: F) -> Self {
        NoteDataMap { iter, f }
    }
}

impl<T, B, F: FnMut(T) -> B, I: Iterator<Item = GenericNote<T>>> Iterator for NoteDataMap<F, I> {
    type Item = GenericNote<B>;

    fn next(&mut self) -> Option<Self::Item> {
        self.iter.next().map(|note| note.map(&mut self.f))
    }
}

/// Trait to add `map_note_data` method to iterators over notes
pub trait MapNoteData<T>: Sized {
    fn map_note_data<B, F: FnMut(T) -> B>(self, f: F) -> NoteDataMap<F, Self>;
}

impl<T, U> MapNoteData<T> for U
where
    U: Iterator<Item = GenericNote<T>>,
{
    fn map_note_data<B, F: FnMut(T) -> B>(self, f: F) -> NoteDataMap<F, Self> {
        NoteDataMap::new(self, f)
    }
}

pub(crate) fn map_note_text<B>(
    mut f: impl FnMut(&str) -> B,
) -> impl FnMut(&Note) -> GenericNote<B> {
    move |note| GenericNote {
        text: f(&note.text),
        raw: note.raw,
        min: note.min,
    }
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

impl Note {
    pub fn new(contents: &str) -> Self {
        Self {
            text: contents.to_owned(),
            raw: false,
            min: false,
        }
    }
    pub fn map<B, F: Fn(String) -> B>(self, f: F) -> GenericNote<B> {
        let text = f(self.text);

        GenericNote {
            text,
            raw: self.raw,
            min: self.min,
        }
    }
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

impl<T> GenericNote<T> {
    pub fn new(contents: T) -> Self {
        Self {
            text: contents,
            raw: false,
            min: false,
        }
    }

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

impl From<GenericNote<String>> for Note {
    fn from(note: GenericNote<String>) -> Self {
        Self {
            text: note.text,
            raw: note.raw,
            min: note.min,
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
