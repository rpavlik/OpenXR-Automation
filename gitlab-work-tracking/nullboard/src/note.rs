// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use serde::{Deserialize, Serialize};

/// A single "note" or "card" in a Nullboard-compatible format
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq, Default)]
pub struct BasicNote {
    /// Contents of the note
    text: String,
    /// Whether the note is shown "raw" (without a border, makes it look like a sub-header)
    raw: bool,
    /// Whether the note is shown minimized/collapsed
    min: bool,
}

impl crate::traits::Note for BasicNote {
    type Data = String;

    fn min(&self) -> bool {
        self.min
    }

    fn raw(&self) -> bool {
        self.raw
    }

    fn data(&self) -> &Self::Data {
        &self.text
    }

    fn data_mut(&mut self) -> &mut Self::Data {
        &mut self.text
    }
}

impl BasicNote {
    /// Create a new note
    pub fn new(contents: &str) -> Self {
        Self {
            text: contents.to_owned(),
            raw: false,
            min: false,
        }
    }

    /// Create a generic note from this one by applying a mapping transform to its text
    pub fn map<B>(self, f: impl FnOnce(String) -> B) -> GenericNote<B> {
        let data = f(self.text);

        GenericNote {
            data,
            raw: self.raw,
            min: self.min,
        }
    }
}

/// Nullboard list note, with arbitrary data type
///
/// See also `Note`
#[derive(Clone, PartialEq, Eq, Default)]
pub struct GenericNote<T> {
    /// Data of the note - corresponds to `text` in `Note`
    pub data: T,
    /// Whether the note is shown "raw" (without a border, makes it look like a sub-header)
    pub raw: bool,
    /// Whether the note is shown minimized/collapsed
    pub min: bool,
}

impl<T> crate::traits::Note for GenericNote<T> {
    type Data = T;

    fn min(&self) -> bool {
        self.min
    }

    fn raw(&self) -> bool {
        self.raw
    }

    fn data(&self) -> &Self::Data {
        &self.data
    }

    fn data_mut(&mut self) -> &mut Self::Data {
        &mut self.data
    }
}

impl<T> GenericNote<T> {
    /// Create a new generic note
    pub fn new(data: T) -> Self {
        Self {
            data,
            raw: false,
            min: false,
        }
    }

    /// Map the data of a note
    pub fn map<B>(self, f: impl FnOnce(T) -> B) -> GenericNote<B> {
        let data = f(self.data);

        GenericNote {
            data,
            raw: self.raw,
            min: self.min,
        }
    }
}

pub(crate) fn map_note_text<B>(
    mut f: impl FnMut(&str) -> B,
) -> impl FnMut(&BasicNote) -> GenericNote<B> {
    move |note| GenericNote {
        data: f(&note.text),
        raw: note.raw,
        min: note.min,
    }
}

pub(crate) fn map_note_data_string<B>(
    mut f: impl FnMut(String) -> B,
) -> impl FnMut(BasicNote) -> GenericNote<B> {
    move |note| GenericNote {
        data: f(note.text),
        raw: note.raw,
        min: note.min,
    }
}
impl<T: core::fmt::Debug> core::fmt::Debug for GenericNote<T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("GenericNote")
            .field("data", &self.data)
            .field("raw", &self.raw)
            .field("min", &self.min)
            .finish()
    }
}

impl From<GenericNote<String>> for BasicNote {
    fn from(note: GenericNote<String>) -> Self {
        Self {
            text: note.data,
            raw: note.raw,
            min: note.min,
        }
    }
}

impl From<BasicNote> for GenericNote<String> {
    fn from(note: BasicNote) -> Self {
        Self {
            data: note.text,
            raw: note.raw,
            min: note.min,
        }
    }
}
