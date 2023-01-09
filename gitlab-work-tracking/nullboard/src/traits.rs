// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{GenericList, GenericNote};

/// Data access methods applicable to all types that resemble a note/card on a Kanban board (or sub-headings)
pub trait Note {
    type Data;

    /// Create a new note with the given text/data
    fn from_data(data: Self::Data) -> Self;

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
/// Data access methods applicable to all types that resemble a list of notes/Kanban board column
pub trait List {
    type NoteType: Note;

    /// Create a new list with the given title
    fn from_title(title: &str) -> Self;

    /// Title of the list
    fn title(&self) -> &str;

    /// Notes in the list (as a slice)
    fn notes(&self) -> &[Self::NoteType];

    /// Notes in the list (as a mutable reference to a vector)
    fn notes_mut(&mut self) -> &mut Vec<Self::NoteType>;

    /// Filter notes using a predicate on their data
    fn filter_notes<F: FnMut(&<Self::NoteType as Note>::Data) -> bool>(self, f: F) -> Self;

    /// Transform notes using a function on their data
    fn map_note_data<B, F: FnMut(<Self::NoteType as Note>::Data) -> B>(
        self,
        f: F,
    ) -> GenericList<B>;

    /// Push a note created with default options and the given data/
    fn push_note_with_data(&mut self, data: <Self::NoteType as Note>::Data) {
        self.notes_mut()
            .push(<Self::NoteType as Note>::from_data(data))
    }
}

/// Things that are collections of lists but not necessarily having all the data of a Board.
pub trait ListCollection {
    type List: List;

    /// Try getting a list named the given string, if one exists
    fn named_list(&self, name: &str) -> Option<&Self::List>;

    /// Try getting a list named the given string, if one exists
    fn named_list_mut(&mut self, name: &str) -> Option<&mut Self::List>;

    /// Append a new list
    fn push_list(&mut self, list: Self::List) -> &mut Self::List;

    /// Append a new list with the given title
    fn push_list_with_title(&mut self, title: &str) -> &mut Self::List {
        self.push_list(<Self::List as List>::from_title(title))
    }
}

/// Trait implemented by things that look like boards.
pub trait Board: ListCollection {
    /// Title of the board
    fn title(&self) -> &str;

    /// ID of the board
    fn id(&self) -> u64;

    /// History slice
    fn history(&self) -> &[u32];

    /// Get the current revision number
    fn revision(&self) -> u32;

    /// The read-only format constant
    fn format(&self) -> u32;

    /// Return a clone of this board, with an updated revision number and history.
    fn make_new_revision(&self) -> Self;

    /// Increment the revision number, and place the old one on the history list.
    fn increment_revision(&mut self);

    /// Make a new revision that replaces the lists.
    fn make_new_revision_with_lists(self, lists: impl IntoIterator<Item = Self::List>) -> Self;

    /// Take all the lists
    fn take_lists(&mut self) -> Vec<Self::List>;
}

impl<T: List> ListCollection for Vec<T> {
    type List = T;

    fn named_list(&self, name: &str) -> Option<&Self::List> {
        self.iter().find(|&list| list.title() == name)
    }

    fn named_list_mut(&mut self, name: &str) -> Option<&mut Self::List> {
        self.iter_mut().find(|list| list.title() == name)
    }

    fn push_list(&mut self, list: Self::List) -> &mut Self::List {
        self.push(list);
        self.last_mut()
            .expect("we just pushed it so it must be there")
    }
}
