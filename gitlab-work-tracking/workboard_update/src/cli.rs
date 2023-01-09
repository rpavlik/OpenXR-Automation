// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use clap::Args;
use gitlab::GitlabBuilder;
use gitlab_work_units::ProjectMapper;
use log::info;
use std::path::{Path, PathBuf};

#[derive(Args, Debug, Clone)]
pub struct GitlabArgs {
    /// Domain name hosting your GitLab instance
    #[arg(long = "gitlab", env = "GL_DOMAIN")]
    pub gitlab_domain: String,

    /// Private access token to use when accessing GitLab.
    #[arg(long = "token", env = "GL_ACCESS_TOKEN", hide_env_values = true)]
    pub gitlab_access_token: String,
}

impl GitlabArgs {
    pub fn as_gitlab_builder(&self) -> GitlabBuilder {
        info!("Connecting to GitLab: {}", &self.gitlab_domain);
        GitlabBuilder::new(&self.gitlab_domain, &self.gitlab_access_token)
    }
}

#[derive(Args, Debug, Clone)]
pub struct InputOutputArgs {
    /// The JSON export from Nullboard (or compatible format) - usually ends in .nbx
    #[arg()]
    pub filename: PathBuf,

    /// Output filename: the extension .nbx is suggested. Will be computed if not specified.
    #[arg(short, long)]
    pub output: Option<PathBuf>,
}

#[derive(Debug, thiserror::Error)]
#[error("Could not determine the input filename stem to compute a default output filename")]
pub struct OutputFileStemError;

pub fn compute_default_output_filename(path: &Path) -> Result<PathBuf, OutputFileStemError> {
    path.file_stem()
        .map(|p| {
            let mut p = p.to_owned();
            p.push(".updated.nbx");
            p
        })
        .map(|file_name| path.with_file_name(file_name))
        .ok_or(OutputFileStemError {})
}

impl InputOutputArgs {
    pub fn try_output_path(&self) -> Result<PathBuf, OutputFileStemError> {
        self.output.clone().map_or_else(
            // come up with a default output name
            || compute_default_output_filename(&self.filename),
            // or wrap our existing one in Ok
            Ok,
        )
    }
}

#[derive(Args, Debug, Clone)]
pub struct ProjectArgs {
    /// Fully qualified project name to assume for MRs and issues with no project specified
    #[arg(long, short = 'p', env = "GL_DEFAULT_PROJECT")]
    pub default_project: String,

    /// How to format the default project in the output. If not specified, the default project name is omitted from exported text references.
    #[arg(long, env = "GL_DEFAULT_PROJECT_FORMAT_AS")]
    pub default_project_format_as: Option<String>,
}

impl ProjectArgs {
    #[must_use = "constructor"]
    pub fn to_project_mapper<'a>(
        &self,
        client: &'a gitlab::Gitlab,
    ) -> Result<ProjectMapper<'a>, gitlab_work_units::Error> {
        info!(
            "Setting up project mapper and querying default project {}",
            &self.default_project
        );
        let mut mapper = ProjectMapper::new(client, &self.default_project)?;
        if let Some(default_formatting) = &self.default_project_format_as {
            info!(
            "When exporting, will explicitly show default project name as and querying default project {}",
            &default_formatting
        );
            mapper.try_set_project_name_formatting(None, default_formatting)?;
        }
        Ok(mapper)
    }
}
