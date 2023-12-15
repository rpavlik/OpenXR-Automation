// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Rylie Pavlik <rylie.pavlik@collabora.com>

use std::iter::once;

use gitlab::{
    api::{common::NameOrId, endpoint_prelude::Method, issues::ProjectIssues, Endpoint, Query},
    IssueInternalId, MergeRequestInternalId, ProjectId,
};
use gitlab_work_units::{BaseGitLabItemReference, ProjectItemReference};
use log::warn;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct References {
    // short: String,
    full: String,
}

#[derive(Debug, Deserialize)]
pub struct IssueData {
    project_id: ProjectId,
    iid: IssueInternalId,
    title: String,
    description: String,
    web_url: String,
    // labels: Vec<String>,
    // state: gitlab::IssueState,
    // references: References,
    // has_tasks: bool,
    // task_status: String,
    // task_completion_status: TaskCompletionStatus,
}

impl IssueData {
    pub fn title(&self) -> &str {
        self.title.as_ref()
    }

    pub fn description(&self) -> &str {
        self.description.as_ref()
    }

    pub fn iid(&self) -> IssueInternalId {
        self.iid
    }

    pub fn project_id(&self) -> ProjectId {
        self.project_id
    }

    pub fn web_url(&self) -> &str {
        self.web_url.as_ref()
    }
}

impl From<&IssueData> for gitlab_work_units::Issue {
    fn from(value: &IssueData) -> Self {
        Self::new(value.project_id.into(), value.iid)
    }
}
impl From<IssueData> for gitlab_work_units::Issue {
    fn from(value: IssueData) -> Self {
        Self::new(value.project_id.into(), value.iid)
    }
}

#[derive(Debug, Deserialize)]
pub struct MRData {
    project_id: ProjectId,
    iid: MergeRequestInternalId,
    title: String,
    web_url: String,
    // labels: Vec<String>,
    // state: gitlab::MergeRequestState,
    // description: String,
    // references: References,
}

impl MRData {
    pub fn title(&self) -> &str {
        self.title.as_ref()
    }

    pub fn web_url(&self) -> &str {
        self.web_url.as_ref()
    }
}

impl From<&MRData> for gitlab_work_units::MergeRequest {
    fn from(value: &MRData) -> Self {
        Self::new(value.project_id.into(), value.iid)
    }
}
impl From<MRData> for gitlab_work_units::MergeRequest {
    fn from(value: MRData) -> Self {
        Self::new(value.project_id.into(), value.iid)
    }
}

impl From<&References> for ProjectItemReference {
    fn from(data: &References) -> Self {
        data.full
            .as_str()
            .try_into()
            .expect("we should be able to parse just bare refs from gitlab")
    }
}

impl From<&IssueData> for ProjectItemReference {
    fn from(data: &IssueData) -> Self {
        gitlab_work_units::Issue::new(data.project_id.into(), data.iid).into()
    }
}

impl From<&MRData> for ProjectItemReference {
    fn from(data: &MRData) -> Self {
        gitlab_work_units::MergeRequest::new(data.project_id.into(), data.iid).into()
    }
}

/// Temporary impl to get related merge requests until https://gitlab.kitware.com/utils/rust-gitlab/-/merge_requests/373
/// is merged and released
struct RelatedMergeRequests<'a> {
    project: NameOrId<'a>,
    issue: u64,
}
impl Endpoint for RelatedMergeRequests<'_> {
    fn method(&self) -> gitlab::api::endpoint_prelude::Method {
        Method::GET
    }

    fn endpoint(&self) -> std::borrow::Cow<'static, str> {
        format!(
            "projects/{}/issues/{}/related_merge_requests",
            self.project, self.issue
        )
        .into()
    }
}

#[derive(Debug, thiserror::Error)]
pub enum QueryError {
    #[error("Error trying to find related merge requests for #{0}: {1}")]
    RelatedMRForIssue(
        ProjectItemReference,
        #[source] Box<dyn std::error::Error + Send + Sync>,
    ),

    #[error("Query for issues failed: {0}")]
    Issues(#[source] Box<dyn std::error::Error + Send + Sync>),

    #[error("Query for merge requests failed: {0}")]
    MRs(#[source] Box<dyn std::error::Error + Send + Sync>),
}

pub fn find_related_mrs(
    client: &gitlab::Gitlab,
    project_name: &str,
    issue: &gitlab_work_units::Issue,
) -> Result<Vec<MRData>, QueryError> {
    let current_issue = ProjectItemReference::from(issue.clone());

    let related_endpoint = RelatedMergeRequests {
        issue: issue.raw_iid(),
        project: project_name.into(),
    };
    let vec: Vec<MRData> = related_endpoint
        .query(client)
        .map_err(|e| QueryError::RelatedMRForIssue(current_issue.clone(), Box::new(e)))?;
    Ok(vec)
}

pub fn find_issues<'a>(
    client: &'a gitlab::Gitlab,
    endpoint: ProjectIssues,
) -> Result<FindIssues<'a>, QueryError> {
    let vec: Vec<IssueData> = gitlab::api::paged(endpoint, gitlab::api::Pagination::All)
        .query(client)
        .map_err(|e| QueryError::Issues(Box::new(e)))?;
    Ok(FindIssues { client, vec })
}

pub struct FindIssues<'a> {
    client: &'a gitlab::Gitlab,
    vec: Vec<IssueData>,
}

impl<'a> std::ops::Deref for FindIssues<'a> {
    type Target = Vec<IssueData>;

    fn deref(&self) -> &Self::Target {
        &self.vec
    }
}

impl<'a> FindIssues<'a> {
    pub fn and_related_mrs(
        self,
        project_name: &'a str,
    ) -> impl 'a + Iterator<Item = (IssueData, Vec<ProjectItemReference>)> {
        self.vec.into_iter().map(|issue| {
            let issue_ref = gitlab_work_units::Issue::from(&issue);
            let current = ProjectItemReference::from(issue_ref.clone());
            let references = find_related_mrs(self.client, project_name, &issue_ref)
                .map(|v| -> Vec<ProjectItemReference> {
                    once(current.clone())
                        .chain(
                            v.into_iter()
                                .map(gitlab_work_units::MergeRequest::from)
                                .map(ProjectItemReference::from),
                        )
                        .collect()
                })
                .unwrap_or_else(|e| {
                    warn!(
                        "Error trying to find related merge requests for #{}: {}",
                        &current, e
                    );
                    vec![current]
                });
            (issue, references)
        })
    }
}

pub fn find_mrs<'a>(
    client: &'a gitlab::Gitlab,
    endpoint: gitlab::api::projects::merge_requests::MergeRequests<'a>,
) -> Result<impl 'a + Iterator<Item = (MRData, Vec<ProjectItemReference>)>, QueryError> {
    let vec: Vec<MRData> = gitlab::api::paged(endpoint, gitlab::api::Pagination::All)
        .query(client)
        .map_err(|e| QueryError::MRs(Box::new(e)))?;

    Ok(vec.into_iter().map(|mr| {
        let reference = ProjectItemReference::from(&mr);
        (mr, vec![reference])
    }))
}
