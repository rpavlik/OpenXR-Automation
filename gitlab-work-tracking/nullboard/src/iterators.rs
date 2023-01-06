// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{List, Note};

/// Adapters for iterators over notes
pub mod over_notes {
    use crate::{GenericNote, Note};

    /// Iterator adapter for mapping note data when iterating over notes.
    #[must_use = "iterators are lazy"]
    pub struct MapNoteData<I, F> {
        iter: I,
        f: F,
    }

    impl<I, F> MapNoteData<I, F> {
        pub(super) fn new(iter: I, f: F) -> Self {
            MapNoteData { iter, f }
        }
    }

    impl<B, I, F> Iterator for MapNoteData<I, F>
    where
        I: Iterator,
        I::Item: Note,
        F: FnMut(<I::Item as Note>::Data) -> B,
    {
        type Item = GenericNote<B>;

        #[inline]
        fn next(&mut self) -> Option<Self::Item> {
            self.iter.next().map(|note| note.map_note_data(&mut self.f))
        }

        #[inline]
        fn size_hint(&self) -> (usize, Option<usize>) {
            // no change
            self.iter.size_hint()
        }
    }
}

/// Trait to add `map_note_data` method to iterators over notes
pub trait NoteIteratorAdapters<T>: Sized {
    /// Maps the data of the notes (like calling GenericNote::map on each element)
    fn map_note_data<B, F: FnMut(T) -> B>(self, f: F) -> over_notes::MapNoteData<Self, F>;
}

// This impl cannot be combined with the trait declaration above or it won't work.
impl<T, I> NoteIteratorAdapters<T> for I
where
    I: Iterator,
    I::Item: Note<Data = T>,
{
    fn map_note_data<B, F: FnMut(T) -> B>(self, f: F) -> over_notes::MapNoteData<Self, F> {
        over_notes::MapNoteData::new(self, f)
    }
}

/// Adapters for iterators over lists
pub mod over_lists {
    use crate::{GenericList, List};
    use std::marker::PhantomData;

    /// Iterator adapter for mapping note data when iterating over lists.
    #[must_use = "iterators are lazy"]
    pub struct MapNoteData<'a, I, F> {
        iter: I,
        f: F,
        phantom: PhantomData<&'a str>,
    }

    impl<I, F> MapNoteData<'_, I, F> {
        pub(super) fn new(iter: I, f: F) -> Self {
            MapNoteData {
                iter,
                f,
                phantom: PhantomData,
            }
        }
    }

    impl<'a, B, I, F> Iterator for MapNoteData<'a, I, F>
    where
        F: FnMut(<I::Item as List>::NoteData) -> B,
        I: Iterator + Sized,
        I::Item: List<'a>,
    {
        type Item = GenericList<'a, B>;

        #[inline]
        fn next(&mut self) -> Option<Self::Item> {
            self.iter.next().map(|list| list.map_note_data(&mut self.f))
        }

        #[inline]
        fn size_hint(&self) -> (usize, Option<usize>) {
            // no change
            self.iter.size_hint()
        }
    }

    /// Iterator adapter for filtering notes (by their data) when iterating over lists.
    #[must_use = "iterators are lazy"]
    pub struct FilterNotes<'a, I, P> {
        iter: I,
        predicate: P,
        phantom: PhantomData<&'a str>,
    }

    impl<'a, I: Iterator, P: 'a> FilterNotes<'a, I, P> {
        pub(super) fn new(iter: I, predicate: P) -> Self {
            FilterNotes {
                iter,
                predicate,
                phantom: PhantomData,
            }
        }
    }

    impl<'a, I, P> Iterator for &mut FilterNotes<'a, I, P>
    where
        I: Iterator,
        I::Item: List<'a>,
        for<'b> P: 'a + FnMut(&'b <I::Item as List>::NoteData) -> bool,
    {
        type Item = I::Item;

        #[inline]
        fn next(&mut self) -> Option<Self::Item> {
            self.iter
                .next()
                .map(|list| list.filter_notes(&mut self.predicate))
        }

        #[inline]
        fn size_hint(&self) -> (usize, Option<usize>) {
            // Only know the upper bound
            (0, self.iter.size_hint().1)
        }
    }
}

/// Trait to add adapter methods to iterators over lists
pub trait ListIteratorAdapters<'a, T>: Sized {
    /// Maps the data of the notes in each list (like calling `GenericList::map_note_data` on each list)
    fn map_note_data<B, F: FnMut(T) -> B>(self, f: F) -> over_lists::MapNoteData<'a, Self, F>;

    /// Filters the notes (by their data) in each list (like calling `GenericList::filter_notes` on each list)
    fn filter_notes<P: 'a + FnMut(&T) -> bool>(
        self,
        predicate: P,
    ) -> over_lists::FilterNotes<'a, Self, P>;
}

// This impl cannot be combined with the trait declaration above or it won't work.
impl<'a, T, I> ListIteratorAdapters<'a, T> for I
where
    I: 'a + Iterator,
    I::Item: List<'a, NoteData = T>,
    T: 'a,
{
    fn map_note_data<B, F: FnMut(T) -> B>(self, f: F) -> over_lists::MapNoteData<'a, Self, F> {
        over_lists::MapNoteData::new(self, f)
    }

    fn filter_notes<P: 'a + FnMut(&T) -> bool>(
        self,
        predicate: P,
    ) -> over_lists::FilterNotes<'a, Self, P> {
        over_lists::FilterNotes::new(self, predicate)
    }
}
