import logging
from typing import Optional, cast
import gitlab.v4.objects
from gitlab.v4.objects import ProjectMergeRequest
from datetime import datetime
import zoneinfo

from openxr_ops.priority_results import is_note_a_push

# from .checklists import ReleaseChecklistCollection

# from .vendors import VendorNames


def _yield_merge_request_notes(
    mr: ProjectMergeRequest,
    include_users: list[str],
    not_before: datetime,
    not_after: Optional[datetime] = None,
):
    log = logging.getLogger("_yield_merge_request_notes")

    for n in mr.notes.list(order_by="updated_at", iterator=True):
        note = cast(gitlab.v4.objects.ProjectMergeRequestNote, n)
        # note.pprint()
        updated = datetime.fromisoformat(note.attributes["updated_at"]).replace(
            tzinfo=zoneinfo.ZoneInfo("UTC")
        )
        if not_after is not None:
            if updated > not_after:
                log.debug(
                    "Skipping, updated datestamp of %s is newer than not_after date of %s",
                    updated.isoformat(),
                    not_after.isoformat(),
                )
        if updated < not_before:
            log.info(
                "Ending note iteration, reached %s which is earlier than our not_before date of %s",
                updated.isoformat(),
                not_before.isoformat(),
            )
            return
        user = note.attributes["author"]["username"]
        if note.attributes["author"]["username"] not in include_users:
            log.debug("Skipping note from user %s", user)
            continue
        yield note


class MRActivity:
    """Information on selected activity for an MR."""

    def __init__(
        self,
        mr: ProjectMergeRequest,
        include_users: list[str],
        not_before: datetime,
        not_after: Optional[datetime] = None,
    ):
        # include_users: list[str]
        # not_before: datetime,
        # not_after: Optional[datetime] = None,
        self.mr: ProjectMergeRequest = mr
        self._log = logging.getLogger(f"MRActivity({mr.title})")

        if not_after is None:
            self._log.info(
                "Retrieving activity since %s by %s",
                not_before.isoformat(),
                ", ".join(include_users),
            )
        else:

            self._log.info(
                "Retrieving activity between %s and %s by %s",
                not_before.isoformat(),
                not_after.isoformat(),
                ", ".join(include_users),
            )
            pass
        self.pushes = []
        self.inline_comments = []
        self.other_comments = []
        for note in _yield_merge_request_notes(
            mr=self.mr,
            include_users=include_users,
            not_before=not_before,
            not_after=not_after,
        ):
            if "position" in note.attributes:
                # This is an in-line comment/discussion
                self.inline_comments.append(note)
            elif note.system:
                # this might be a push, or a notification of change.
                if is_note_a_push(note):
                    self.pushes.append(note)
                # otherwise it's a "user changed this in version xyz" in an inline comment
            else:
                # this is just a comment
                self.other_comments.append(note)

        # pushes = [
        #     cast(gitlab.v4.objects.ProjectMergeRequestNote, n)
        #     for n in self.mr_notes
        #     if is_note_a_push(cast(gitlab.v4.objects.ProjectMergeRequestNote, n))
        # ]


if __name__ == "__main__":
    from .gitlab import OpenXRGitlab

    import argparse

    parser = argparse.ArgumentParser()

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    oxr_gitlab = OpenXRGitlab.create()

    mr_num = 2963  # XR_META_body_tracking_calibration
    mr: ProjectMergeRequest = oxr_gitlab.main_proj.mergerequests.get(mr_num)
    users = ["rpavlik", "haagch", "safarimonkey"]
    # not_before = datetime(2024, 11, 1, tzinfo=zoneinfo.ZoneInfo("UTC"))
    not_before = datetime(2025, 7, 1, tzinfo=zoneinfo.ZoneInfo("UTC"))

    activity = MRActivity(mr, include_users=users, not_before=not_before)

    mr.discussions.list(iterator=True)
    print(len(activity.inline_comments), "inline comments")
    print(len(activity.pushes), "pushes")
    print(len(activity.other_comments), "other comments")

    # log.info("Performing startup queries")
    # vendor_names = VendorNames.from_git(oxr_gitlab.main_proj)
    # collection = ReleaseChecklistCollection(
    #     oxr_gitlab.main_proj,
    #     oxr_gitlab.operations_proj,
    #     checklist_factory=None,
    #     vendor_names=vendor_names,
    # )

    # try:
    #     collection.load_config("ops_issues.toml")
    # except IOError:
    #     print("Could not load config")

    # collection.load_initial_data()
