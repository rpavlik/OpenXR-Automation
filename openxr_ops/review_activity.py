import csv
import logging
from datetime import datetime
from typing import Optional
import zoneinfo
from pprint import pprint

from openxr_ops.checklists import ReleaseChecklistCollection
from openxr_ops.vendors import VendorNames
from .gitlab import OpenXRGitlab
from .mr_stats import MRActivity, users


def _get_timestamp(item):
    if "updated_at" in item:
        return item["updated_at"]
    if "created_at" in item:
        return item["created_at"]
    pprint(item)
    raise RuntimeError("help")


def dump_huge_csv(
    fn,
    oxr_gitlab,
    exclude: list[str],
    not_before: datetime,
    not_after: Optional[datetime] = None,
):
    log.info("Performing startup queries")
    vendor_names = VendorNames.from_git(oxr_gitlab.main_proj)
    collection = ReleaseChecklistCollection(
        oxr_gitlab.main_proj,
        oxr_gitlab.operations_proj,
        checklist_factory=None,
        vendor_names=vendor_names,
    )

    try:
        collection.load_config("ops_issues.toml")
    except IOError:
        print("Could not load config")

    # collection.load_initial_data(all_closed=True)
    collection.load_initial_data(deep=True)

    with open(fn, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(
            [
                "Issue Title",
                "MR",
                "Timestamp",
                "Username",
                "ActionType",
            ]
        )
        for issue in collection.issue_to_mr.keys():
            issue_obj = collection.issue_str_to_cached_issue_object(issue)

            if not issue_obj:
                continue
            title = issue_obj.attributes["title"]
            for exclusion in exclude:
                if exclusion in title:
                    log.info("Skipping %s due to exclusion rule", title)
                    continue

            log.info("Processing actions for %s", title)
            mr_num = collection.issue_to_mr[issue]
            mr = oxr_gitlab.main_proj.mergerequests.get(mr_num)
            activity = MRActivity(
                mr,
                include_users=users,
                not_before=not_before,
                not_after=not_after,
                deep_discussions=True,
            )
            for item in activity.inline_comments:
                timestamp = _get_timestamp(item.attributes)
                user = item.attributes["author"]["username"]
                writer.writerow([title, str(mr_num), timestamp, user, "InlineComment"])

            for item in activity.pushes:
                timestamp = _get_timestamp(item.attributes)
                user = item.attributes["author"]["username"]
                writer.writerow([title, str(mr_num), timestamp, user, "Push"])

            for item in activity.other_comments:
                timestamp = _get_timestamp(item.attributes)
                user = item.attributes["author"]["username"]
                writer.writerow([title, str(mr_num), timestamp, user, "OtherComment"])
            fp.flush()


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--exclude",
        type=str,
        nargs="*",
        help="Exclude any extension whose issue title includes this string",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)
    exclude = []
    if args.exclude:
        log.info("Excluding %s", ", ".join(args.exclude))
        exclude = list(args.exclude)

    oxr_gitlab = OpenXRGitlab.create()

    dump_huge_csv(
        "mr_review_events_since_nov1.csv",
        oxr_gitlab,
        exclude,
        not_before=datetime(2024, 11, 1, tzinfo=zoneinfo.ZoneInfo("UTC")),
        # not_after=datetime(2025, 7, 31, tzinfo=zoneinfo.ZoneInfo("UTC")),
    )
