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
    insert_outcome::{InsertOutcome, UnitCreated, UnitNotUpdated, UnitUpdated},
    UnitId, WorkUnit,
};
use itertools::Itertools;
use log::{debug, warn};
use std::{
    borrow::Borrow,
    cell::RefCell,
    collections::{
        hash_map::{Entry, OccupiedEntry, VacantEntry},
        HashMap, HashSet,
    },
    fmt::Debug,
    hash::Hash,
    ops::DerefMut,
    rc::Rc,
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
    R: Hash + Debug + Eq + Clone + AsRef<R>,
{
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

            let mut pending = PendingRefGroup::new(unit_by_ref, ref_ids);
            debug!("Given {} unique refs", pending.len());

            let unique_existing_unit_ids: Vec<UnitId> = pending.unique_units().collect();

            let existing_unit_id = unique_existing_unit_ids.first().map(|id| *id);
            let unit_id = existing_unit_id.unwrap_or_else(|| units.0.next_key());

            // let ref_ids_to_merge: Vec<RefId> = unique_existing_unit_ids
            //     .into_iter()
            //     .skip(1)
            //     .flat_map(|id| {
            //         units
            //             .get_unit_mut(id)
            //             .expect("Internal ID")
            //             .extinct_by(unit_id)
            //             .into_iter()
            //     })
            //     .collect();

            // Mark the units we're merging from, and take their refs and add them to our list of stuff to update.
            let pending = pending.extend(unique_existing_unit_ids.iter().skip(1).flat_map(|id| {
                units
                    .get_unit_mut(*id)
                    .expect("Internal ID")
                    .extinct_by(unit_id)
                    .into_iter()
            }));
            // let pending = pending.extend(ref_ids_to_merge);

            let unit = existing_unit_id.map(|id| {
                units
                    .get_unit_mut(id)
                    .expect("this ID came from the internal map")
            });

            let assigned = pending.assign(unit_id);
            let refs_added = assigned.new_refs.len();
            // let moved_refs = assigned.moved_refs.len();
            if let Some(unit) = unit {
                // let merge_results = unique_existing_ids
                //     .iter()
                //     .skip(1)
                //     .map(|&src_id| {
                //         debug!("Merging {} into {}", src_id, unit_id);
                //         self.merge_work_units(unit_id, *src_id)?;
                //         Ok(())
                //     })
                //     .collect();
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
                Ok(InsertOutcome::NotUpdated(UnitNotUpdated { unit_id }))
            } else {
                Ok(InsertOutcome::Updated(UnitUpdated {
                    unit_id,
                    refs_added,
                    units_merged_in,
                }))
            }
        }
    }

    // // Return value is number of refs added
    // fn add_refs_to_unit_id<'a, I, T>(
    //     &mut self,
    //     unit_id: UnitId,
    //     refs: I,
    // ) -> Result<usize, GetUnitIdError>
    // where
    //     I: IntoIterator<Item = T>,
    //     T: Hash + Eq + Debug + 'a + CloneOrTake<R> + AsRef<R>, //+ Borrow<R>,
    //                                                            // R: Clone,
    //                                                            // T: Hash + Eq + ToOwned + Debug,
    //                                                            // &'a T: CloneOrTake<R> + Borrow<R>,
    //                                                            // R: Clone + Borrow<&'a T>,
    //                                                            // T: Hash + Eq + ToOwned + Debug + CloneOrTake<R> + Borrow<R> + 'a,
    // {
    //     let mut count: usize = 0;
    //     for reference in refs.into_iter() {
    //         if self.add_ref_to_unit_id(unit_id, reference)? {
    //             count += 1;
    //         }
    //     }
    //     Ok(count)
    // }

    // /// Returns Ok(true) if a ref was added
    // fn add_ref_to_unit_id<'a, T>(
    //     &'a mut self,
    //     id: UnitId,
    //     reference: T,
    // ) -> Result<bool, GetUnitIdError>
    // where
    //     T: Hash + Eq + Debug + CloneOrTake<R> + AsRef<R> + 'a, // + ToOwned
    // {
    //     debug!(
    //         "Trying to add a reference to {}: {:?}",
    //         id,
    //         reference.borrow()
    //     );
    //     let owned = R::clone(reference.as_ref());
    //     let do_insert = match self.unit_by_ref_id.entry(R::clone(reference.as_ref())) {
    //         Entry::Occupied(mut entry) => {
    //             if entry.get() != &id {
    //                 debug!(
    //                     "Reference previously in {} being moved to {}: {:?}",
    //                     entry.get(),
    //                     id,
    //                     reference.borrow()
    //                 );
    //                 *entry.get_mut() = id;
    //                 true
    //             } else {
    //                 debug!("Reference already in {}: {:?}", id, reference.borrow());
    //                 false
    //             }
    //         }
    //         Entry::Vacant(entry) => {
    //             // no existing
    //             entry.insert(id);
    //             true
    //         }
    //     };
    //     if do_insert {
    //         let unit = self.units.get_unit_mut(id)?;
    //         debug!("New reference added to {}: {:?}", id, reference.borrow());
    //         unit.add_ref(reference.clone_or_take());
    //     }
    //     Ok(do_insert)
    // }

    // fn merge_work_units(&mut self, id: UnitId, src_id: UnitId) -> Result<(), GetUnitIdError>
    // where
    //     R: Clone + Debug + CloneOrTake<R> + AsRef<R>,
    // {
    //     let src = self.units.get_unit_mut(src_id)?;
    //     debug!(
    //         "Merging {} into {}, and marking the former extinct",
    //         src_id, id
    //     );
    //     // mark as extinct, and add its refs to the other work unit
    //     let refs_to_move = src.extinct_by(id);
    //     for reference in refs_to_move {
    //         self.add_ref_to_unit_id(id, reference)?;
    //     }
    //     debug!("Merging {} into {} done", src_id, id);
    //     Ok(())
    // }

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

    // /// Find the set of unit IDs corresponding to the refs, if any.
    // fn get_ids_for_refs<I, T>(&self, refs: I) -> Vec<UnitId>
    // where
    //     // R: AsRef<T> + Clone,
    //     I: ExactSizeIterator<Item = T>,
    //     T: AsRef<R>, // T: Hash + Eq + ToOwned + Debug + CloneOrTake<R> + Clone + Borrow<R>,
    // {
    //     let mut units: Vec<UnitId> = vec![];
    //     let mut retrieved_ids: HashSet<UnitId> = Default::default();

    //     debug!(
    //         "Finding units for a collection of {} references",
    //         refs.len()
    //     );
    //     for reference in refs.into_iter() {
    //         if let Some(&id) = self.unit_by_ref_id.get(reference.as_ref()) {
    //             debug!("Found id {} for: {:?}", id, reference.as_ref());
    //             if retrieved_ids.insert(id) {
    //                 debug!("Adding {} to our return set", id);
    //                 units.push(id);
    //             }
    //         } else {
    //             debug!("Do not yet know {:?}", reference.as_ref())
    //         }
    //     }
    //     debug!(
    //         "Found {} unique work unit IDs for the provided {} references",
    //         units.len(),
    //         refs.len()
    //     );
    //     units
    // }

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

    /// Make a

    /// Create a new work unit from the given reference and return its id
    fn emplace(&mut self, reference: R) -> UnitId {
        self.0.push_and_get_key(WorkUnit::new(reference))
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
    use crate::{UnitId, WorkUnitCollection};

    #[test]
    fn test_collection() {
        let collection: WorkUnitCollection<i32> = Default::default();
        assert!(collection.get_unit(UnitId::from(1)).is_err());
    }
}
