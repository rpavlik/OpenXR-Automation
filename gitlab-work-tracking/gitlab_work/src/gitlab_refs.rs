// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::collections::HashMap;

use gitlab::{IssueInternalId, MergeRequestInternalId, Project, ProjectId};

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum ProjectReference {
    ProjectId(ProjectId),
    ProjectName(String),
    UnknownProject,
}

impl Default for ProjectReference {
    fn default() -> Self {
        ProjectReference::UnknownProject
    }
}

pub(crate) trait SimpleGitLabItemReference: Clone {
    type IidType: Copy;

    /// Get the project for this reference
    fn get_project(&self) -> &ProjectReference;

    /// Get the iid (per project ID) of this reference
    fn get_iid(&self) -> Self::IidType;

    /// Get the iid (per project ID) of this reference
    fn get_raw_iid(&self) -> u64;

    /// Get the symbol used to signify a reference of this type
    fn get_symbol() -> &'static str;

    /// Clone and replace project with the given project ID
    fn with_project_id(&self, project_id: ProjectId) -> Self;
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Issue {
    project: ProjectReference,
    iid: IssueInternalId,
}

impl Issue {
    pub fn new(project: ProjectReference, iid: IssueInternalId) -> Self {
        Self { project, iid }
    }
}

impl SimpleGitLabItemReference for Issue {
    type IidType = IssueInternalId;

    fn get_project(&self) -> &ProjectReference {
        &self.project
    }

    fn get_iid(&self) -> Self::IidType {
        self.iid
    }
    fn get_raw_iid(&self) -> u64 {
        self.iid.value()
    }

    fn get_symbol() -> &'static str {
        "#"
    }

    fn with_project_id(&self, project_id: ProjectId) -> Self {
        Self {
            project: ProjectReference::ProjectId(project_id),
            iid: self.iid,
        }
    }
}

impl Into<Issue> for gitlab::types::Issue {
    fn into(self) -> Issue {
        Issue {
            project: ProjectReference::ProjectId(self.project_id),
            iid: self.iid,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct MergeRequest {
    pub(crate) project: ProjectReference,
    pub(crate) iid: MergeRequestInternalId,
}

impl MergeRequest {
    pub fn new(project: ProjectReference, iid: MergeRequestInternalId) -> Self {
        Self { project, iid }
    }
}
impl SimpleGitLabItemReference for MergeRequest {
    type IidType = MergeRequestInternalId;

    fn get_project(&self) -> &ProjectReference {
        &self.project
    }

    fn get_iid(&self) -> Self::IidType {
        self.iid
    }
    fn get_raw_iid(&self) -> u64 {
        self.iid.value()
    }

    fn get_symbol() -> &'static str {
        "!"
    }

    fn with_project_id(&self, project_id: ProjectId) -> Self {
        Self {
            project: ProjectReference::ProjectId(project_id),
            iid: self.iid,
        }
    }
}

impl Into<MergeRequest> for gitlab::types::MergeRequest {
    fn into(self) -> MergeRequest {
        MergeRequest {
            project: ProjectReference::ProjectId(self.project_id),
            iid: self.iid,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum ProjectItemReference {
    Issue(Issue),
    MergeRequest(MergeRequest),
}

impl Into<ProjectItemReference> for Issue {
    fn into(self) -> ProjectItemReference {
        ProjectItemReference::Issue(self)
    }
}

impl Into<ProjectItemReference> for MergeRequest {
    fn into(self) -> ProjectItemReference {
        ProjectItemReference::MergeRequest(self)
    }
}
