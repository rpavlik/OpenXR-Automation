// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use anyhow::Error;
use gitlab_work::{
    note::LineOrReference, BaseGitLabItemReference, GitLabItemReferenceNormalize,
    ProjectItemReference, ProjectMapper, UnitId, WorkUnitCollection,
};
use itertools::Itertools;
use log::warn;
use nullboard_tools::{GenericList, GenericNote};

#[must_use = "iterators are lazy and do nothing unless consumed"]
#[derive(Clone)]
pub struct NoteIterMapper<I, F> {
    iter: I,
    f: F,
}
impl<I, F> NoteIterMapper<I, F> {
    pub fn new(iter: I, f: F) -> Self {
        Self { iter, f }
    }
}

impl<T, B, I: Iterator<Item = GenericNote<T>>, F> Iterator for NoteIterMapper<I, F>
where
    F: FnMut(T) -> B,
{
    type Item = GenericNote<B>;

    fn next(&mut self) -> Option<Self::Item> {
        self.iter.next().map(|note| note.map(&mut self.f))
    }
}

// #[must_use = "iterators are lazy and do nothing unless consumed"]
// #[derive(Clone)]
// pub struct ListIterMapper<I, F> {
//     iter: I,
//     f: F,
// }
// impl<I, F> ListIterMapper<I, F> {
//     pub fn new(iter: I, f: F) -> Self {
//         Self { iter, f }
//     }
// }

// impl<T, B, I: Iterator<Item = GenericList<T>>, F> Iterator for ListIterMapper<I, F>
// where
//     F: FnMut(T) -> B,
// {
//     type Item = GenericList<B>;

//     fn next(&mut self) -> Option<Self::Item> {
//         // outer map is on Option
//         self.iter.next().map(|list| list.map_notes(self.f))
//     }
// }

// pub fn map_note_data_in_lists<T, B, I: Iterator<Item = GenericList<T>>, F: FnMut(T) -> B>(
//     lists_iter: I,
//     f: F,
// ) -> ListIterMapper<I, F> {
//     ListIterMapper::new(lists_iter, f)
// }

#[must_use = "iterators are lazy and do nothing unless consumed"]
#[derive(Clone)]
pub struct NoteFilterMap<I, F> {
    iter: I,
    f: F,
}
impl<I, F> NoteFilterMap<I, F> {
    pub fn new(iter: I, f: F) -> Self {
        Self { iter, f }
    }
}

// fn notes_filter_map<T, B>(
//     mut f: impl FnMut(T) -> Option<B>,
// ) -> impl FnMut(GenericList<T>) -> GenericList<B> {
//     move |list: GenericList<T>| GenericList {
//         title: list.title,
//         notes: list.notes.into_iter().filter_map(f).collect(),
//     }
// }
// fn list_filter_map<T, B>(
//     mut f: impl FnMut(GenericNote<T>) -> Option<GenericNote<B>>,
// ) -> impl FnMut(GenericList<T>) -> GenericList<B> {
//     move |list: GenericList<T>| GenericList {
//         title: list.title,
//         notes: list.notes.into_iter().filter_map(f).collect(),
//     }
// }
// impl<T, B, I: Iterator<Item = GenericList<T>>, F> Iterator for NoteFilterMap<I, F>
// where
//     F: FnMut(T) -> Option<B>,
// {
//     type Item = GenericList<B>;

//     fn next(&mut self) -> Option<Self::Item> {
//         // outer map is on Option
//         self.iter.find_map(|list| GenericList {
//             title: list.title,
//             notes: list.notes.into_iter().filter_map(self.f).collect(),
//         })

//         // and_then(f) map(|list| list.map_notes(self.f))
//     }
// }

pub fn map_note_data_in_lists<'a, T, B, F: 'a + FnMut(T) -> B>(
    lists: impl IntoIterator<Item = GenericList<T>> + 'a,
    mut f: F,
) -> impl Iterator<Item = GenericList<B>> + 'a {
    // "move" moves f into the closure, &mut avoids moving it *out* of the closure in each call
    let map_list = move |list: GenericList<T>| -> GenericList<B> { list.map_notes(&mut f) };

    lists.into_iter().map(map_list)
}
