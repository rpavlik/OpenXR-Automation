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

    fn map_note_data<B, F: FnMut(Self::Data) -> B>(self, mut f: F) -> GenericNote<B> {
        let data = f(self.text);

        GenericNote {
            data,
            raw: self.raw,
            min: self.min,
        }
    }

    fn from_data(data: Self::Data) -> Self {
        BasicNote::new(&data)
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

    fn from_data(data: Self::Data) -> Self {
        GenericNote::new(data)
    }

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

    fn map_note_data<B, F: FnMut(Self::Data) -> B>(self, mut f: F) -> GenericNote<B> {
        let data = f(self.data);

        GenericNote {
            data,
            raw: self.raw,
            min: self.min,
        }
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
