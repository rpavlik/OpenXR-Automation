// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

#[derive(Debug)]
pub struct GenericNote<T>
where
    T: core::fmt::Debug,
{
    /// Contents of the note
    pub text: T,
    /// Whether the note is shown "raw" (without a border, makes it look like a sub-header)
    pub raw: bool,
    /// Whether the note is shown minimized/collapsed
    pub min: bool,
}

impl<T: core::fmt::Debug> GenericNote<T> {
    pub fn map<B: core::fmt::Debug>(self, f: impl FnOnce(T) -> B) -> GenericNote<B> {
        let text = f(self.text);

        GenericNote {
            text,
            raw: self.raw,
            min: self.min,
        }
    }
}

#[derive(Debug)]
pub struct GenericList<T: core::fmt::Debug> {
    /// Title of the list
    pub title: String,
    /// Notes in the list
    pub notes: Vec<GenericNote<T>>,
}

fn map_generic_note_text<T: core::fmt::Debug, B: core::fmt::Debug>(
    mut f: impl FnMut(T) -> B,
) -> impl FnMut(GenericNote<T>) -> GenericNote<B> {
    move |note| GenericNote {
        text: f(note.text),
        raw: note.raw,
        min: note.min,
    }
}

impl<T: core::fmt::Debug> GenericList<T> {
    pub fn map_note_text<U: core::fmt::Debug, F: FnMut(T) -> U>(self, f: F) -> GenericList<U> {
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
