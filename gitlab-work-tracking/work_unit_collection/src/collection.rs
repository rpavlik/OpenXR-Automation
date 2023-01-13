// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{
    error::{
        ExtinctWorkUnitId, FollowExtinctionUnitIdError, GetUnitIdError, InsertError,
        InvalidWorkUnitId, NoReferencesError, RecursionLimitReached,
    },
    insert_outcome::{InsertOutcome, UnitCreated, UnitUnchanged, UnitUpdated},
    UnitId, WorkUnit,
};
use itertools::Itertools;
use log::{debug, warn};
use std::{
    collections::{hash_map::Entry, HashMap, HashSet},
    fmt::Debug,
    hash::Hash,
};
use typed_index_collections::TiVec;

#[derive(Default, Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct RefId(usize);

impl From<usize> for RefId {
    fn from(value: usize) -> Self {
        RefId(value)
    }
}
impl From<RefId> for usize {
    fn from(value: RefId) -> Self {
        value.0
    }
}

/// Owner of reference data: assigns each unique reference an ID which is easier to manipulate
#[derive(Debug, Default)]
struct RefLookup<R> {
    ref_contents: TiVec<RefId, R>,
    ref_map: HashMap<R, RefId>,
}

impl<R> RefLookup<R>
where
    R: Clone + Hash + Eq,
{
    fn new() -> Self {
        Self {
            ref_contents: Default::default(),
            ref_map: Default::default(),
        }
    }

    fn get_or_create_id_for_ref(&mut self, r: &R) -> RefId {
        if let Some(ref_id) = self.ref_map.get(r) {
            return *ref_id;
        }
        let ref_id = self.ref_contents.push_and_get_key(r.clone());
        self.ref_map.insert(r.clone(), ref_id);
        ref_id
    }

    fn get_or_create_id_for_owned_ref(&mut self, r: R) -> RefId {
        if let Some(ref_id) = self.ref_map.get(&r) {
            return *ref_id;
        }
        let ref_id = self.ref_contents.push_and_get_key(r.clone());
        self.ref_map.insert(r, ref_id);
        ref_id
    }

    fn find_id(&self, r: &R) -> Option<RefId> {
        self.ref_map.get(r).copied()
    }

    fn get_reference(&self, ref_id: RefId) -> Option<&R> {
        self.ref_contents.get(ref_id)
    }
}

/// A container for "work units" that are ordered collections of unique "item references" (initial use case is GitLab project item references: issues and MRs).
/// Any given item reference can only belong to a single work unit, and each work unit has an ID.
/// To ensure there are not multiple references to a work unit, recommend normalizing the project item reference first.
#[derive(Debug, Default)]
pub struct WorkUnitCollection<R> {
    units: UnitContainer<RefId>,
    unit_by_ref_id: HashMap<RefId, UnitId>,
    refs: RefLookup<R>,
}

impl<R> WorkUnitCollection<R>
where
    R: Hash + Debug + Eq + Clone + Default,
{
    pub fn new() -> Self {
        Default::default()
    }

    /// Records a work unit containing the provided references (must be non-empty).
    /// If any of those references already exist in the work collection, their corresponding work units are merged.
    /// Any references not yet in the work collection are added.
    pub fn add_or_get_unit_for_refs<'a, I>(
        &'a mut self,
        refs: I,
    ) -> Result<InsertOutcome, InsertError>
    where
        I: IntoIterator<Item = R>,
        R: Clone,
    {
        let ref_ids: Vec<RefId> = refs
            .into_iter()
            .map(|r| self.refs.get_or_create_id_for_owned_ref(r))
            .collect();

        let (unique_existing_ids, unit_id, refs_added) = {
            let Self {
                ref mut units,
                unit_by_ref_id: ref mut unit_by_ref,
                refs: _,
            } = self;

            let pending = PendingRefGroup::new(unit_by_ref, ref_ids);
            debug!("Given {} unique refs", pending.len());

            let unique_existing_unit_ids: Vec<UnitId> = pending.unique_units().collect();

            let existing_unit_id = unique_existing_unit_ids.first().map(|id| *id);
            let unit_id = existing_unit_id.unwrap_or_else(|| units.0.next_key());

            // Mark the units we're merging from, and take their refs and add them to our list of stuff to update.
            let pending = pending.extend(unique_existing_unit_ids.iter().skip(1).flat_map(|id| {
                units
                    .get_unit_mut(*id)
                    .expect("Internal ID")
                    .extinct_by(unit_id)
                    .into_iter()
            }));

            let unit = existing_unit_id.map(|id| {
                units
                    .get_unit_mut(id)
                    .expect("this ID came from the internal map")
            });

            let assigned = pending.assign(unit_id);
            let refs_added = assigned.new_refs.len();
            if let Some(unit) = unit {
                unit.extend_refs(assigned.moved_refs.into_iter());
                unit.extend_refs(assigned.new_refs.into_iter());
            } else {
                assert!(assigned.moved_refs.is_empty());
                let confirmed_unit_id = units.push_from_iterator(assigned.new_refs.into_iter());
                assert_eq!(unit_id, confirmed_unit_id);
            }
            (unique_existing_unit_ids, unit_id, refs_added)
        };

        // Now we may merge, since we no longer hold an existing mutable borrow
        // let mut units_merged_in: usize = 0;
        // for &src_id in unique_existing_ids.iter().fuse().skip(1) {
        //     self.merge_work_units(unit_id, src_id)?;
        //     units_merged_in += 1;
        // }

        let units_merged_in = unique_existing_ids.len().saturating_sub(1);

        if unique_existing_ids.is_empty() {
            Ok(InsertOutcome::Created(UnitCreated {
                unit_id,
                refs_added,
            }))
        } else {
            if refs_added == 0 && units_merged_in == 0 {
                Ok(InsertOutcome::Unchanged(UnitUnchanged { unit_id }))
            } else {
                Ok(InsertOutcome::Updated(UnitUpdated {
                    unit_id,
                    refs_added,
                    units_merged_in,
                }))
            }
        }
    }

    /// Get a work unit by ID
    pub fn get_unit(&self, id: UnitId) -> Result<&WorkUnit<RefId>, GetUnitIdError> {
        self.units.get_unit(id)
    }

    /// Folow extinction pointers to get the valid unit ID after all populating and merging is complete
    pub fn get_unit_id_following_extinction(
        &self,
        id: UnitId,
        limit: usize,
    ) -> Result<UnitId, FollowExtinctionUnitIdError> {
        self.units.follow_extinction(id, limit)
    }

    pub fn len(&self) -> usize {
        self.units.len()
    }

    pub fn is_empty(&self) -> bool {
        self.units.is_empty()
    }
}

trait CloneOrTake<T> {
    fn clone_or_take(self) -> T;
}
impl<T> CloneOrTake<T> for T {
    fn clone_or_take(self) -> T {
        self
    }
}

impl<T: Clone> CloneOrTake<T> for &T {
    fn clone_or_take(self) -> T {
        Clone::clone(&self)
    }
}

// trait AsRefCloneTake<T> {
//     type Value;
//     // fn ref_borrow(&self) -> &Self::Value;
//     fn ref_clone(&self) -> Self::Value;
//     fn ref_take(self) -> Self::Value;
// }
// impl<T> AsRefCloneTake<T> for &T
// where
//     T: Hash + Eq + Clone + Borrow<T>,
// {
//     type Value = T;
//     // fn ref_borrow(&self) -> &R {
//     //     self
//     // }

//     fn ref_clone(&self) -> T {
//         Clone::clone(self)
//     }

//     fn ref_take(self) -> T {
//         Clone::clone(self)
//     }
// }
// impl<T> AsRefCloneTake<T> for T
// where
//     T: Hash + Eq + Clone + Borrow<T>,
// {
//     type Value = T;

//     fn ref_clone(&self) -> Self::Value {
//         Clone::clone(&self)
//     }

//     fn ref_take(self) -> Self::Value {
//         self
//     }
// }

// pub trait RefLookup {
//     type Reference;
//     fn lookup_ref_id(&self, ref_id: RefId) -> Option<&Self::Reference>;
// }

struct PendingRefGroup<'a> {
    hash_map: &'a mut HashMap<RefId, UnitId>,
    added: HashSet<RefId>,
    occupied: Vec<(RefId, UnitId)>,
    vacant: Vec<RefId>,
    // unique_units: Vec<&'a UnitId>,
}

impl<'a> PendingRefGroup<'a> {
    fn len(&self) -> usize {
        self.occupied.len() + self.vacant.len()
    }
    fn extend(self, refs: impl IntoIterator<Item = RefId>) -> PendingRefGroup<'a> {
        refs.into_iter()
            .fold(self, |grp, r| grp.with_additional_entry(r))
        // let _: Vec<_> = refs.into_iter().map(|r| self.insert(r)).collect();
        // for reference in refs.into_iter() {
        //     self.insert(reference);
        // }
    }

    fn insert(&'a mut self, r: RefId) {
        if self.added.insert(r) {
            match self.hash_map.entry(r) {
                Entry::Occupied(entry) => self.occupied.push((r, *entry.get())),
                Entry::Vacant(_) => self.vacant.push(r),
            }
        }
    }

    fn with_additional_entry(mut self, r: RefId) -> PendingRefGroup<'a>
    where
        Self: 'a,
    {
        // self.insert(r);

        if self.added.insert(r) {
            match self.hash_map.entry(r) {
                Entry::Occupied(entry) => self.occupied.push((r, *entry.get())),
                Entry::Vacant(_) => self.vacant.push(r),
            }
        }
        self
    }

    fn new(
        hash_map: &'a mut HashMap<RefId, UnitId>,
        refs: impl IntoIterator<Item = RefId>,
    ) -> Self {
        let occupied = vec![];
        let vacant = vec![];

        Self {
            hash_map,
            added: Default::default(),
            occupied,
            vacant,
        }
        .extend(refs)
    }

    fn unique_units(&'a self) -> impl Iterator<Item = UnitId> + 'a {
        self.occupied.iter().map(|(_, unit_id)| *unit_id).unique()
    }

    fn iter_refs(&'a self) -> impl Iterator<Item = &'a RefId> + 'a {
        self.occupied
            .iter()
            .map(|(ref_id, _)| ref_id)
            .chain(self.vacant.iter())
    }

    fn assign(self, unit_id: UnitId) -> AssignedRefGroup<RefId> {
        let moved_refs: Vec<RefId> = self
            .occupied
            .iter()
            .filter_map(|(ref_id, existing_unit_id)| {
                if existing_unit_id != &unit_id {
                    debug!(
                        "Reference previously in {} being moved to {}: {:?}",
                        existing_unit_id, unit_id, ref_id
                    );
                    self.hash_map.insert(*ref_id, unit_id);
                    Some(*ref_id)
                } else {
                    debug!("Reference already in {}: {:?}", unit_id, ref_id);
                    None
                }
            })
            .collect();

        let new_refs: Vec<RefId> = self
            .vacant
            .iter()
            .map(|ref_id| {
                self.hash_map.insert(*ref_id, unit_id);
                *ref_id
            })
            .collect();
        AssignedRefGroup {
            moved_refs,
            new_refs,
        }
    }
}

struct AssignedRefGroup<R> {
    // hash_map: HashMap<R, UnitId>,
    moved_refs: Vec<R>,
    new_refs: Vec<R>,
}
// struct UnitLookup<R>(HashMap<R, UnitId>);
// impl<R> UnitLookup<R>
// where
//     R: Hash + Eq,
// {
//     // pub fn add_or_get_unit_for_refs(&mut self, refs: Vec<R>) -> Result<(), InsertError> {
//     //     // let entries: Vec<_> = refs.into_iter().map(|r| self.0.entry(r)).collect();
//     //     let mut occupied = vec![];
//     //     let mut vacant = vec![];
//     //     for r in refs {
//     //         match self.0.entry(r) {
//     //             Entry::Occupied(entry) =>occupied.push(entry),
//     //             Entry::Vacant(entry) => vacant.push(entry),
//     //         }
//     //     }
//     //     let units: Vec<_> = occupied.iter().map(|entry| entry.get()).unique().collect();

//     //     entries.iter().filter_map(|e| if let Entry::Occupied(entry) = e {
//     //         Ok(entry.)
//     //     } else { false })

//     //     Ok(())
//     // }
// }

/// Internal newtype to provide utility functions over a TiVec<UnitId, WorkUnit>
/// `R` is your "ItemReference" type: e.g. for GitLab, it would be an enum that can refer
/// to an issue or merge request.
#[derive(Default)]
struct UnitContainer<R>(TiVec<UnitId, WorkUnit<R>>);

impl<R> Debug for UnitContainer<R>
where
    R: Debug,
{
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_tuple("UnitContainer").field(&self.0).finish()
    }
}
impl<R> UnitContainer<R> {
    /// Get a mutable work unit by ID
    fn get_unit_mut(&mut self, id: UnitId) -> Result<&mut WorkUnit<R>, GetUnitIdError> {
        let unit = self.0.get_mut(id).ok_or(InvalidWorkUnitId(id))?;
        if let Some(extincted_by) = &unit.extincted_by() {
            return Err(ExtinctWorkUnitId(id, *extincted_by).into());
        }
        Ok(unit)
    }

    /// Get a work unit by ID
    fn get_unit(&self, id: UnitId) -> Result<&WorkUnit<R>, GetUnitIdError> {
        let unit = self.0.get(id).ok_or(InvalidWorkUnitId(id))?;
        if let Some(extincted_by) = &unit.extincted_by() {
            return Err(ExtinctWorkUnitId(id, *extincted_by).into());
        }
        Ok(unit)
    }

    /// Create a new work unit from the given references and return its id
    fn push_from_iterator(&mut self, iter: impl Iterator<Item = R>) -> UnitId {
        self.0.push_and_get_key(WorkUnit::from_iterator(iter))
    }

    /// If the ID is extinct, follow the extincted-by field, repeatedly, at most `limit` steps.
    fn follow_extinction(
        &self,
        id: UnitId,
        limit: usize,
    ) -> Result<UnitId, FollowExtinctionUnitIdError> {
        let mut result_id = id;
        for _i in 0..limit {
            let unit = self.0.get(result_id).ok_or(InvalidWorkUnitId(id))?;
            match unit.extincted_by() {
                Some(successor) => {
                    warn!(
                        "Following extinction pointer: {} to {}",
                        &result_id, successor
                    );
                    result_id = successor;
                }
                None => return Ok(result_id),
            }
        }
        Err(RecursionLimitReached(id).into())
    }

    pub fn len(&self) -> usize {
        self.0.len()
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use std::iter::once;

    use crate::{
        insert_outcome::{InsertOutcome, UnitCreated},
        InsertOutcomeGetter, UnitId, WorkUnitCollection,
    };

    #[test]
    fn test_collection() {
        let mut collection: WorkUnitCollection<i32> = Default::default();
        assert!(collection.get_unit(UnitId::from(1)).is_err());
        const A: i32 = 1;
        const B: i32 = 2;
        const C: i32 = 3;
        const D: i32 = 4;

        let unit_for_a = {
            let outcome_a = collection
                .add_or_get_unit_for_refs(once(A))
                .expect("we passed at least one");
            assert!(outcome_a.is_created());
            assert_eq!(outcome_a.refs_added(), 1);
            outcome_a.into_work_unit_id()
        };

        // A is in a work unit
        assert_eq!(collection.len(), 1);

        {
            let outcome_a_again = collection
                .add_or_get_unit_for_refs(once(A))
                .expect("we passed at least one");
            assert!(outcome_a_again.is_unchanged());
            assert_eq!(outcome_a_again.work_unit_id(), unit_for_a);
        }

        {
            let outcome_ab = collection
                .add_or_get_unit_for_refs(vec![A, B].into_iter())
                .unwrap();

            assert!(outcome_ab.is_updated());
            assert_eq!(outcome_ab.work_unit_id(), unit_for_a);
            assert_eq!(outcome_ab.refs_added(), 1);
        }

        // A and B are now in one work unit
        let unit_for_ab = unit_for_a;
        assert_eq!(collection.len(), 1);

        let unit_for_c = {
            let outcome_c = collection.add_or_get_unit_for_refs(once(C)).unwrap();
            assert!(outcome_c.is_created());
            assert_eq!(outcome_c.refs_added(), 1);
            outcome_c.into_work_unit_id()
        };

        // C is now in its own work unit
        assert_ne!(unit_for_ab, unit_for_c);
        assert_eq!(collection.len(), 2);

        // Check to make sure that doing A or B again doesn't change things
        {
            let outcome_a_again = collection.add_or_get_unit_for_refs(once(A)).unwrap();
            assert!(outcome_a_again.is_unchanged());
            assert_eq!(outcome_a_again.work_unit_id(), unit_for_ab);
        }

        {
            let outcome_b_again = collection.add_or_get_unit_for_refs(once(B)).unwrap();
            assert!(outcome_b_again.is_unchanged());
            assert_eq!(outcome_b_again.work_unit_id(), unit_for_ab);
        }

        // Now request A, B, C, D as a single group: merge!
        let outcome_abcd = collection
            .add_or_get_unit_for_refs(vec![A, B, C, D].into_iter())
            .unwrap();
        assert!(outcome_abcd.is_updated());
        assert_eq!(outcome_abcd.units_merged(), 1);
        assert_eq!(outcome_abcd.refs_added(), 1);
        assert_eq!(outcome_abcd.work_unit_id(), unit_for_ab);

        // the old work unit we had for C is now extinct.
        assert!(collection.get_unit(unit_for_c).is_err());
        assert_eq!(
            collection
                .get_unit_id_following_extinction(unit_for_c, 5)
                .unwrap(),
            unit_for_a
        );
    }
}
