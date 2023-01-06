// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::fmt::Display;

use gitlab::{api::common::NameOrId, IssueInternalId, MergeRequestInternalId, ProjectId};

/// A way of referring to a project.
/// More than one name may correspond to a single project ID.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum ProjectReference {
    ProjectId(ProjectId),
    ProjectName(String),
    UnknownProject,
}

impl ProjectReference {
    pub fn project_id(&self) -> Option<ProjectId> {
        match self {
            ProjectReference::ProjectId(id) => Some(*id),
            ProjectReference::ProjectName(_) => None,
            ProjectReference::UnknownProject => None,
        }
    }
}

#[derive(Debug, thiserror::Error)]
#[error("Cannot pass ProjectReference::UnknownProject into the gitlab API")]
pub struct UnknownProjectError;

impl<'a> TryInto<NameOrId<'a>> for &'a ProjectReference {
    type Error = UnknownProjectError;

    fn try_into(self) -> Result<NameOrId<'a>, Self::Error> {
        match self {
            ProjectReference::ProjectId(id) => Ok(id.value().into()),
            ProjectReference::ProjectName(name) => Ok(name.clone().into()),
            ProjectReference::UnknownProject => Err(UnknownProjectError),
        }
    }
}

impl From<ProjectId> for ProjectReference {
    fn from(id: ProjectId) -> Self {
        ProjectReference::ProjectId(id)
    }
}

impl From<&ProjectId> for ProjectReference {
    fn from(id: &ProjectId) -> Self {
        ProjectReference::ProjectId(*id)
    }
}

impl From<&str> for ProjectReference {
    fn from(s: &str) -> Self {
        ProjectReference::ProjectName(s.to_owned())
    }
}

impl From<String> for ProjectReference {
    fn from(s: String) -> Self {
        ProjectReference::ProjectName(s)
    }
}

impl From<Option<&str>> for ProjectReference {
    fn from(s: Option<&str>) -> Self {
        s.map(|s| s.into()).unwrap_or_default()
    }
}

impl From<&Option<&str>> for ProjectReference {
    fn from(s: &Option<&str>) -> Self {
        (*s).into()
    }
}

impl Default for ProjectReference {
    fn default() -> Self {
        ProjectReference::UnknownProject
    }
}

pub trait BaseGitLabItemReference: Clone {
    /// Get the project for this reference
    fn project(&self) -> &ProjectReference;

    /// Get the project for this reference (mutable)
    fn project_mut(&mut self) -> &mut ProjectReference;

    /// Get the iid (per project ID) of this reference
    fn raw_iid(&self) -> u64;

    /// Clone and replace project with the given project reference
    fn clone_with_project(&self, project: ProjectReference) -> Self;

    /// Consume and replace project with the given project reference
    fn with_project(self, project: ProjectReference) -> Self;

    /// Get the symbol used to signify a reference of the type of this instance
    fn symbol(&self) -> char;

    /// Clone and replace project with the given project ID
    fn clone_with_project_id(&self, project_id: ProjectId) -> Self {
        self.clone_with_project(project_id.into())
    }
}

pub trait TypedGitLabItemReference: BaseGitLabItemReference {
    type IidType: Copy;

    /// Get the symbol used to signify a reference of this type, without an instance
    fn symbol_static() -> char;

    /// Get the iid (per project ID) of this reference
    fn iid(&self) -> Self::IidType;
}

pub fn format_reference(
    project: &ProjectReference,
    symbol: char,
    raw_iid: u64,
    f: &mut std::fmt::Formatter<'_>,
) -> std::fmt::Result {
    match project {
        ProjectReference::ProjectId(id) => {
            write!(f, "{}{}{}", id, symbol, raw_iid)
        }
        ProjectReference::ProjectName(name) => {
            write!(f, "{}{}{}", name, symbol, raw_iid)
        }
        ProjectReference::UnknownProject => {
            write!(f, "{}{}", symbol, raw_iid)
        }
    }
}

pub fn format_reference_using_trait<T: TypedGitLabItemReference>(
    reference: &T,
    f: &mut std::fmt::Formatter<'_>,
) -> std::fmt::Result {
    format_reference(
        reference.project(),
        T::symbol_static(),
        reference.raw_iid(),
        f,
    )
}

pub const ISSUE_SYMBOL: char = '#';

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

impl BaseGitLabItemReference for Issue {
    fn project(&self) -> &ProjectReference {
        &self.project
    }

    fn project_mut(&mut self) -> &mut ProjectReference {
        &mut self.project
    }

    fn raw_iid(&self) -> u64 {
        self.iid.value()
    }

    fn clone_with_project(&self, project: ProjectReference) -> Self {
        Self {
            project,
            iid: self.iid,
        }
    }

    fn with_project(self, project: ProjectReference) -> Self {
        Self {
            project,
            iid: self.iid,
        }
    }

    fn symbol(&self) -> char {
        Self::symbol_static()
    }
}

impl TypedGitLabItemReference for Issue {
    type IidType = IssueInternalId;

    fn symbol_static() -> char {
        ISSUE_SYMBOL
    }

    fn iid(&self) -> Self::IidType {
        self.iid
    }
}

// TODO: Can we blanket implement Display for anything implementing the trait?
impl Display for Issue {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        format_reference_using_trait(self, f)
    }
}

impl From<gitlab::types::Issue> for Issue {
    fn from(issue: gitlab::types::Issue) -> Self {
        Self {
            project: issue.project_id.into(),
            iid: issue.iid,
        }
    }
}

pub const MR_SYMBOL: char = '!';

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

impl BaseGitLabItemReference for MergeRequest {
    fn project(&self) -> &ProjectReference {
        &self.project
    }

    fn project_mut(&mut self) -> &mut ProjectReference {
        &mut self.project
    }

    fn raw_iid(&self) -> u64 {
        self.iid.value()
    }

    fn clone_with_project(&self, project: ProjectReference) -> Self {
        Self {
            project,
            iid: self.iid,
        }
    }

    fn with_project(self, project: ProjectReference) -> Self {
        Self {
            project,
            iid: self.iid,
        }
    }

    fn symbol(&self) -> char {
        Self::symbol_static()
    }
}

impl TypedGitLabItemReference for MergeRequest {
    type IidType = MergeRequestInternalId;

    fn symbol_static() -> char {
        MR_SYMBOL
    }
    fn iid(&self) -> Self::IidType {
        self.iid
    }
}

impl Display for MergeRequest {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        format_reference_using_trait(self, f)
    }
}

impl From<gitlab::types::MergeRequest> for MergeRequest {
    fn from(src: gitlab::types::MergeRequest) -> Self {
        MergeRequest {
            project: src.project_id.into(),
            iid: src.iid,
        }
    }
}

/// A reference to an item (issue, MR) in a project
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum ProjectItemReference {
    Issue(Issue),
    MergeRequest(MergeRequest),
}

impl From<MergeRequest> for ProjectItemReference {
    fn from(other: MergeRequest) -> Self {
        ProjectItemReference::MergeRequest(other)
    }
}

impl From<Issue> for ProjectItemReference {
    fn from(other: Issue) -> Self {
        ProjectItemReference::Issue(other)
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

impl BaseGitLabItemReference for ProjectItemReference {
    fn project(&self) -> &ProjectReference {
        match self {
            ProjectItemReference::Issue(c) => c.project(),
            ProjectItemReference::MergeRequest(c) => c.project(),
        }
    }

    fn project_mut(&mut self) -> &mut ProjectReference {
        match self {
            ProjectItemReference::Issue(c) => c.project_mut(),
            ProjectItemReference::MergeRequest(c) => c.project_mut(),
        }
    }

    fn raw_iid(&self) -> u64 {
        match self {
            ProjectItemReference::Issue(c) => c.raw_iid(),
            ProjectItemReference::MergeRequest(c) => c.raw_iid(),
        }
    }

    fn clone_with_project(&self, project: ProjectReference) -> Self {
        match self {
            ProjectItemReference::Issue(c) => c.clone_with_project(project).into(),
            ProjectItemReference::MergeRequest(c) => c.clone_with_project(project).into(),
        }
    }

    fn with_project(self, project: ProjectReference) -> Self {
        match self {
            ProjectItemReference::Issue(c) => c.with_project(project).into(),
            ProjectItemReference::MergeRequest(c) => c.with_project(project).into(),
        }
    }

    fn symbol(&self) -> char {
        match self {
            ProjectItemReference::MergeRequest(_) => MergeRequest::symbol_static(),
            ProjectItemReference::Issue(_) => Issue::symbol_static(),
        }
    }
}
