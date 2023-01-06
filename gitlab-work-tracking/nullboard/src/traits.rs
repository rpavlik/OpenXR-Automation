// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{GenericList, GenericNote};

/// Data access methods applicable to all types that resemble a list of notes/Kanban board column
pub trait List<'a> {
    type Note: Note;
    type NoteData;

    /// Title of the list
    fn title(&self) -> &str;

    /// Notes in the list (as a slice)
    fn notes(&self) -> &[Self::Note];

    /// Notes in the list (as a mutable reference to a vector)
    fn notes_mut(&mut self) -> &mut Vec<Self::Note>;

    /// Filter notes using a predicate on their data
    fn filter_notes<F: FnMut(&Self::NoteData) -> bool>(self, f: F) -> Self;

    fn map_note_data<B, F: FnMut(Self::NoteData) -> B>(self, f: F) -> GenericList<'a, B>;
}

/// Data access methods applicable to all types that resemble a note/card on a Kanban board (or sub-headings)
pub trait Note {
    type Data;

    /// Returns true if the note is shown minimized/collapsed
    fn min(&self) -> bool;

    /// Returns true if the note is shown "raw"
    /// (without a border, makes it look like a sub-heading)
    fn raw(&self) -> bool;

    /// Borrow the contents/text of the note
    fn data(&self) -> &Self::Data;

    /// Mutably borrow the contents/text of the note
    fn data_mut(&mut self) -> &mut Self::Data;

    /// Create a new note from this one by applying a mapping/transform to its text/data
    fn map_note_data<B, F: FnMut(Self::Data) -> B>(self, f: F) -> GenericNote<B>;
}
