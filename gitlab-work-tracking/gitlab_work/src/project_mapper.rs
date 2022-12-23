// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{
    gitlab_refs::{ProjectReference, SimpleGitLabItemReference},
    Error,
};
use gitlab::{api, api::Query, ProjectId};
use serde::Deserialize;
use std::collections::HashMap;

pub(crate) struct ProjectMapper {
    client: gitlab::Gitlab,
    default_project_name: String,
    name_to_id: HashMap<String, ProjectId>,
}

#[derive(Debug, Deserialize)]
struct ProjectQuery {
    path: String,
    path_with_namespace: String,
    id: ProjectId,
}

impl ProjectMapper {
    pub(crate) fn new(client: gitlab::Gitlab, default_project: &str) -> Self {
        Self {
            client,
            default_project_name: default_project.to_owned(),
            name_to_id: Default::default(),
        }
    }

    pub(crate) fn lookup_name(&mut self, name: Option<&str>) -> Result<ProjectId, Error> {
        // this keeps the borrow of the default internal
        let name = name.unwrap_or_else(|| &self.default_project_name);

        if let Some(&id) = self.name_to_id.get(name) {
            return Ok(id);
        }
        let endpoint = api::projects::Project::builder().project(name).build()?;
        let proj: ProjectQuery = endpoint
            .query(&self.client)
            .map_err(|e| Error::ProjectQueryError(name.to_owned(), e))?;
        self.name_to_id.insert(proj.path, proj.id);
        self.name_to_id.insert(proj.path_with_namespace, proj.id);
        Ok(proj.id)
    }

    pub(crate) fn map_project_to_id(
        &mut self,
        proj: &ProjectReference,
    ) -> Result<ProjectId, Error> {
        match proj {
            ProjectReference::ProjectId(id) => Ok(*id),
            ProjectReference::ProjectName(name) => self.lookup_name(Some(name)),
            ProjectReference::UnknownProject => self.lookup_name(None),
        }
    }
}

/// Extension trait to `SimpleGitLabItemReference`
pub(crate) trait SimpleGitLabItemReferenceNormalize
where
    Self: Sized,
{
    /// Replace the project reference (of whatever kind) with a ProjectId (numeric reference)
    fn with_normalized_project_reference(&self, mapper: &mut ProjectMapper) -> Result<Self, Error>;
}

impl<T> SimpleGitLabItemReferenceNormalize for T
where
    T: SimpleGitLabItemReference,
{
    fn with_normalized_project_reference(&self, mapper: &mut ProjectMapper) -> Result<Self, Error> {
        let id = mapper.map_project_to_id(self.get_project())?;
        Ok(self.with_project_id(id))
    }
}
