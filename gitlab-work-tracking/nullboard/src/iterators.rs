// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{GenericList, GenericNote, List};

// -- adapters for iterators over notes -- //

pub mod over_notes {
    use crate::GenericNote;

    /// Iterator adapter for mapping note data when iterating over notes.
    #[must_use = "iterators are lazy"]
    pub struct MapNoteData<I, F> {
        iter: I,
        f: F,
    }

    impl<F, I> MapNoteData<I, F> {
        pub(super) fn new(iter: I, f: F) -> Self {
            MapNoteData { iter, f }
        }
    }

    impl<B, T, F, I> Iterator for MapNoteData<I, F>
    where
        F: FnMut(T) -> B,
        I: Iterator<Item = GenericNote<T>>,
    {
        type Item = GenericNote<B>;

        #[inline]
        fn next(&mut self) -> Option<Self::Item> {
            self.iter.next().map(|note| note.map(&mut self.f))
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
impl<T, U> NoteIteratorAdapters<T> for U
where
    U: Iterator<Item = GenericNote<T>>,
{
    fn map_note_data<B, F: FnMut(T) -> B>(self, f: F) -> over_notes::MapNoteData<Self, F> {
        over_notes::MapNoteData::new(self, f)
    }
}

/// Adapters for iterators over lists
pub mod over_lists {
    use crate::{GenericList, List};
    /// Iterator adapter to convert an iterator of List to an iterator of GenericList<String>
    ///
    /// Exists as a struct to work around not being able to name the return type of calling .map()
    /// on an arbitrary iterator in the trait.
    pub struct IntoGeneric<I> {
        iter: I,
    }

    impl<I> IntoGeneric<I> {
        pub(super) fn new(iter: I) -> Self {
            Self { iter }
        }
    }

    impl<I: Iterator<Item = List>> Iterator for IntoGeneric<I> {
        type Item = GenericList<String>;

        #[inline]
        fn next(&mut self) -> Option<Self::Item> {
            self.iter.next().map(List::into_generic)
        }
        #[inline]
        fn size_hint(&self) -> (usize, Option<usize>) {
            // no change
            self.iter.size_hint()
        }
    }

    /// Iterator adapter for mapping note data when iterating over lists.
    #[must_use = "iterators are lazy"]
    pub struct MapNoteData<I, F> {
        iter: I,
        f: F,
    }

    impl<F, I> MapNoteData<I, F> {
        pub(super) fn new(iter: I, f: F) -> Self {
            MapNoteData { iter, f }
        }
    }

    impl<F, I, T, B> Iterator for MapNoteData<I, F>
    where
        F: FnMut(T) -> B,
        I: Iterator<Item = GenericList<T>> + Sized,
    {
        type Item = GenericList<B>;

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
    pub struct FilterNotes<I, P> {
        iter: I,
        predicate: P,
    }

    impl<I, P> FilterNotes<I, P> {
        pub(super) fn new(iter: I, predicate: P) -> Self {
            FilterNotes { iter, predicate }
        }
    }

    impl<I, T, P> Iterator for FilterNotes<I, P>
    where
        I: Iterator<Item = GenericList<T>> + Sized,
        P: FnMut(&T) -> bool,
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
pub trait ListIteratorAdapters<T>: Sized {
    /// Maps the data of the notes in each list (like calling `GenericList::map_note_data` on each list)
    fn map_note_data<B, F: FnMut(T) -> B>(self, f: F) -> over_lists::MapNoteData<Self, F>;

    /// Filters the notes (by their data) in each list (like calling `GenericList::filter_notes` on each list)
    fn filter_notes<P: FnMut(&T) -> bool>(self, predicate: P) -> over_lists::FilterNotes<Self, P>;
}

// This impl cannot be combined with the trait declaration above or it won't work.
impl<T, I> ListIteratorAdapters<T> for I
where
    I: Iterator<Item = GenericList<T>>,
{
    fn map_note_data<B, F: FnMut(T) -> B>(self, f: F) -> over_lists::MapNoteData<Self, F> {
        over_lists::MapNoteData::new(self, f)
    }

    fn filter_notes<P: FnMut(&T) -> bool>(self, predicate: P) -> over_lists::FilterNotes<Self, P> {
        over_lists::FilterNotes::new(self, predicate)
    }
}

/// Trait to add an `into_generic()` method to the result of `Board::take_lists()`
pub trait IntoGenericIter {
    /// Converts each List to a GenericList<String>
    fn into_generic_iter(self) -> over_lists::IntoGeneric<std::vec::IntoIter<List>>;
}

impl IntoGenericIter for Vec<List> {
    fn into_generic_iter(self) -> over_lists::IntoGeneric<std::vec::IntoIter<List>> {
        over_lists::IntoGeneric::new(self.into_iter())
    }
}

/// Trait to add an `into_generic()` method to an iterator over a collection of `List`
pub trait IntoGenericAdapter: Sized {
    /// Converts each List to a GenericList<String>
    fn into_generic(self) -> over_lists::IntoGeneric<Self>;
}

impl<I> IntoGenericAdapter for I
where
    I: Iterator<Item = List>,
{
    fn into_generic(self) -> over_lists::IntoGeneric<Self> {
        over_lists::IntoGeneric::new(self)
    }
}
