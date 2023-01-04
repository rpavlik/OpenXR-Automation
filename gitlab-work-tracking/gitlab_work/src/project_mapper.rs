// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{
    gitlab_refs::{ProjectReference, TypedGitLabItemReference},
    BaseGitLabItemReference, Error,
};
use gitlab::{api, api::Query, ProjectId};
use serde::Deserialize;
use std::collections::{hash_map::Entry, HashMap};

#[derive(Debug, Deserialize)]
struct ProjectQuery {
    path: String,
    path_with_namespace: String,
    id: ProjectId,
}

#[derive(Debug)]
pub struct ProjectMapper {
    client: gitlab::Gitlab,
    default_project_name: String,
    name_to_id: HashMap<String, ProjectId>,
    /// `None` indicates this is the default project and should just be implied, not named
    id_to_formatted_name: HashMap<ProjectId, Option<String>>,
}

impl ProjectMapper {
    /// Create new project mapper object
    pub fn new(client: gitlab::Gitlab, default_project: &str) -> Result<Self, Error> {
        let mut ret = Self {
            client,
            default_project_name: default_project.to_owned(),
            name_to_id: Default::default(),
            id_to_formatted_name: Default::default(),
        };
        // ret.with_default_project_name_formatted_as(default_project)

        let id = ret.try_lookup_name(Some(default_project))?;
        ret.id_to_formatted_name.insert(id, None);
        Ok(ret)
    }

    /// Method to cache a project name and ID, and optionally set custom formatting
    pub fn try_set_project_name_formatting(
        &mut self,
        name: Option<&str>,
        formatting: &str,
    ) -> Result<(), Error> {
        let id = self.try_lookup_name(name)?;
        self.id_to_formatted_name
            .insert(id, Some(formatting.to_owned()));
        Ok(())
    }

    /// Builder method to set a custom formatting of the default project
    pub fn with_default_project_name_formatted_as(
        mut self,
        default_project_name_formatted: &str,
    ) -> Result<Self, Error> {
        self.try_set_project_name_formatting(None, default_project_name_formatted)?;
        Ok(self)
    }

    pub(crate) fn try_lookup_name(&mut self, name: Option<&str>) -> Result<ProjectId, Error> {
        // this keeps the borrow of the default internal
        let name = name.unwrap_or(&self.default_project_name);

        let project_query = match self.name_to_id.entry(name.to_owned()) {
            Entry::Occupied(entry) => return Ok(*entry.get()),
            Entry::Vacant(entry) => {
                let endpoint = api::projects::Project::builder().project(name).build()?;
                let project_query: ProjectQuery = endpoint
                    .query(&self.client)
                    .map_err(|e| Error::ProjectQueryError(name.to_owned(), e))?;
                entry.insert(project_query.id);
                project_query
            }
        };
        let id = project_query.id;

        self.id_to_formatted_name
            .insert(id, Some(project_query.path_with_namespace.clone()));

        // Make sure that both ways of naming a project are in the map (qualified and unqualified)
        if &project_query.path != name {
            self.name_to_id.insert(project_query.path, id);
        }
        if &project_query.path_with_namespace != name {
            self.name_to_id
                .insert(project_query.path_with_namespace, id);
        }
        Ok(id)
    }

    pub fn try_map_project_to_id(&mut self, proj: &ProjectReference) -> Result<ProjectId, Error> {
        match proj {
            ProjectReference::ProjectId(id) => Ok(*id),
            ProjectReference::ProjectName(name) => self.try_lookup_name(Some(name)),
            ProjectReference::UnknownProject => self.try_lookup_name(None),
        }
    }

    pub fn map_id_to_formatted_project(&self, proj: &ProjectReference) -> ProjectReference {
        match proj {
            ProjectReference::ProjectId(id) => self
                .id_to_formatted_name
                .get(id)
                // if the map contained the ID, use the results
                .map(|s| ProjectReference::from(s.as_deref()))
                // otherwise keep using the ID
                .unwrap_or_else(|| ProjectReference::from(id)),
            ProjectReference::ProjectName(_) => proj.clone(),
            ProjectReference::UnknownProject => proj.clone(),
        }
    }
}

/// Extension trait to `BaseGitLabItemReference`
pub trait GitLabItemReferenceNormalize
where
    Self: Sized,
{
    /// Replace the project reference (of whatever kind) with a ProjectId (numeric reference)
    fn try_with_normalized_project_reference(
        &self,
        mapper: &mut ProjectMapper,
    ) -> Result<Self, Error>;

    /// Replace the project reference ID with either a string or "Unknown" (for the default project unless otherwise configured)
    fn with_formatted_project_reference(&self, mapper: &ProjectMapper) -> Self;
}

impl<T> GitLabItemReferenceNormalize for T
where
    T: BaseGitLabItemReference,
{
    fn try_with_normalized_project_reference(
        &self,
        mapper: &mut ProjectMapper,
    ) -> Result<Self, Error> {
        let id = mapper.try_map_project_to_id(self.get_project())?;
        Ok(self.with_project_id(id))
    }

    fn with_formatted_project_reference(&self, mapper: &ProjectMapper) -> Self {
        let id = self.get_project();
        let formatted = mapper.map_id_to_formatted_project(id);
        self.with_project(formatted)
    }
}
