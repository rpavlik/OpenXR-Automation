#!/usr/bin/env python3
# Copyright 2023-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import csv

from openxr import OpenXRGitlab

_MAX_JOB_ROWS = 2000
_MAX_PIPELINE_ROWS = 1000

if __name__ == "__main__":
    oxr_gitlab = OpenXRGitlab.create()
    main_proj = oxr_gitlab.main_proj

    with open("job_stats.csv", "w") as f:
        field_names = ["created", "duration", "status", "name", "web_url"]
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()

        # range is to limit iterations
        for i, job in zip(
            range(_MAX_JOB_ROWS),
            main_proj.jobs.list(scope=["success", "failed"], iterator=True),
        ):
            if i % 100 == 0:
                print("Job record number:", i)
            # print(i, job.attributes["created_at"], job.attributes["name"])
            writer.writerow(
                {
                    "created": job.attributes["created_at"],
                    "duration": job.attributes["duration"],
                    "status": job.attributes["status"],
                    "name": job.attributes["name"],
                    "web_url": job.attributes["web_url"],
                }
            )

    with open("pipeline_stats.csv", "w") as f:
        field_names = ["created", "duration", "source", "ref", "tag", "web_url"]
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()

        # range is to limit iterations
        for i, pipe in zip(
            range(_MAX_PIPELINE_ROWS),
            main_proj.pipelines.list(
                scope=["finished"], status="success", iterator=True
            ),
        ):
            if i % 50 == 0:
                print("Pipeline record number:", i)
            # print(i, job.attributes["created_at"], job.attributes["name"])
            id = pipe.get_id()
            assert id is not None
            full_pipe = main_proj.pipelines.get(id)
            writer.writerow(
                {
                    "created": full_pipe.attributes["created_at"],
                    "duration": full_pipe.attributes["duration"],
                    "source": full_pipe.attributes["source"],
                    "ref": full_pipe.attributes["ref"],
                    "tag": full_pipe.attributes["tag"],
                    "web_url": full_pipe.attributes["web_url"],
                }
            )
