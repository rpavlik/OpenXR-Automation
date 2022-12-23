// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::collections::{HashMap, HashSet};

use gitlab::Project;
use log::debug;
use typed_index_collections::TiVec;

use crate::gitlab_refs::ProjectReference;
use derive_more::{From, Into};

#[derive(Debug)]
pub struct WorkUnit {
    refs: Vec<ProjectReference>,
}

impl WorkUnit {
    pub fn new(projref: ProjectReference) -> Self {
        Self {
            refs: vec![projref],
        }
    }
}

#[derive(Debug, Clone, Copy, From, Into, Hash, PartialEq, Eq, PartialOrd, Ord)]
pub struct UnitId(usize);

#[derive(Debug, Default)]
pub struct WorkUnitCollection {
    units: TiVec<UnitId, WorkUnit>,
    unit_by_ref: HashMap<ProjectReference, UnitId>,
}

impl WorkUnitCollection {
    pub fn add_refs(&mut self, proj: &Project, refs: impl IntoIterator<Item = ProjectReference>) {}

    pub fn try_get_unit(&self, id: UnitId) -> Option<&WorkUnit> {
        self.units.get(id)
    }
    pub fn try_get_unit_mut(&mut self, id: UnitId) -> Option<&mut WorkUnit> {
        self.units.get_mut(id)
    }
    fn get_ids_for_refs(&self, refs: impl IntoIterator<Item = ProjectReference>) -> Vec<UnitId> {
        let mut units: Vec<UnitId> = vec![];
        let mut retrieved_ids: HashSet<UnitId> = Default::default();

        for projref in refs {
            if let Some(&id) = self.unit_by_ref.get(&projref) {
                if retrieved_ids.insert(id) {
                    units.push(id);
                }
            } else {
                debug!("Do not yet know {:#?}", &projref)
            }
        }
        units
    }
}
