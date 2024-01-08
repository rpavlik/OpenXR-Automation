#!/usr/bin/env python3
# Copyright 2023, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import os
import csv

import gitlab
import gitlab.v4.objects

_MAX_ROWS = 2000

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    gl = gitlab.Gitlab(
        url=os.environ["GL_URL"], private_token=os.environ["GL_ACCESS_TOKEN"]
    )

    main_proj = gl.projects.get("openxr/openxr")

    with open("ci_stats.csv", "w") as f:
        field_names = ["created", "duration", "status", "name", "web_url"]
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()

        # range is to limit iterations
        for i, job in zip(
            range(_MAX_ROWS),
            main_proj.jobs.list(scope=["success", "failed"], iterator=True),
        ):
            print(i, job.attributes["created_at"], job.attributes["name"])
            writer.writerow(
                {
                    "created": job.attributes["created_at"],
                    "duration": job.attributes["duration"],
                    "status": job.attributes["status"],
                    "name": job.attributes["name"],
                    "web_url": job.attributes["web_url"],
                }
            )
