// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::{fmt::Display};

use gitlab::{IssueInternalId, MergeRequestInternalId, ProjectId};

/// A way of referring to a project.
/// More than one name may correspond to a single project ID.
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

    fn format(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self.get_project() {
            ProjectReference::ProjectId(id) => {
                write!(f, "{}{}{}", id, Self::get_symbol(), self.get_raw_iid())
            }
            ProjectReference::ProjectName(name) => {
                write!(f, "{}{}{}", name, Self::get_symbol(), self.get_raw_iid())
            }
            ProjectReference::UnknownProject => {
                write!(f, "{}{}", Self::get_symbol(), self.get_raw_iid())
            }
        }
    }
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

impl Display for Issue {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.format(f)
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

impl Display for MergeRequest {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.format(f)
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

/// A reference to an item (issue, MR) in a project
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

impl Display for ProjectItemReference {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ProjectItemReference::Issue(issue) => issue.fmt(f),
            ProjectItemReference::MergeRequest(mr) => mr.fmt(f),
        }
    }
}
