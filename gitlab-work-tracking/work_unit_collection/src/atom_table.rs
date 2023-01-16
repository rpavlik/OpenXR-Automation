// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::{collections::HashMap, hash::Hash};
use typed_index_collections::TiVec;

/// A data structure that lets you use strongly typed indices/keys instead
/// of bulky values, performing a lookup in both directions
#[derive(Debug)]
pub(crate) struct AtomTable<T, I>
where
    I: From<usize> + Copy,
{
    vec: TiVec<I, T>,
    map: HashMap<T, I>,
}

impl<T, I> Default for AtomTable<T, I>
where
    I: From<usize> + Copy,
{
    fn default() -> Self {
        Self {
            vec: Default::default(),
            map: Default::default(),
        }
    }
}

impl<T, I> AtomTable<T, I>
where
    T: Hash + Eq,
    I: From<usize> + Copy,
    usize: From<I>,
{
    pub(crate) fn get_or_create_id_for_owned_value(&mut self, value: T) -> I
    where
        T: Clone,
    {
        if let Some(id) = self.map.get(&value) {
            return *id;
        }
        let id = self.vec.push_and_get_key(value.clone());
        self.map.insert(value, id);
        id
    }

    pub(crate) fn get_id(&self, value: &T) -> Option<I> {
        self.map.get(value).copied()
    }

    pub(crate) fn get_value(&self, id: I) -> Option<&T> {
        self.vec.get(id)
    }
}
