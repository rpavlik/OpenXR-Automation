# Copyright 2022-2026, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import abc
import asyncio
import importlib
import importlib.resources
import logging
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeAlias, cast

import kanboard
from gitlab.v4.objects import ProjectMergeRequest, ProjectMergeRequestNote, User

from ..gitlab import OpenXRGitlab
from ..kanboard_helpers import KanboardProject
from .collection import TaskCollection
from .gitlab import find_task_id
from .load import load_kb_project
from .stages import TaskColumn
from .task import OperationsTask

_MENTION_ACK_EMOJI = "thumbsup"

_LOG = logging.getLogger(__name__)


def _ack_mention(note: ProjectMergeRequestNote):
    note.awardemojis.create(name=_MENTION_ACK_EMOJI)


_dry_run: bool = False


class TriggerType(Enum):
    ASSIGN = 0
    MENTION = 1


@dataclass
class TriggerInfo:
    trigger_type: TriggerType
    username: str | None = None
    user_id: int | None = None

    command_body: str | None = None
    """Only for manual command mentions."""

    note: ProjectMergeRequestNote | None = None
    """Note that performed the command mention."""


@dataclass
class BotConfig:
    bot_user: str
    assignees: dict[str, str] = field(default_factory=dict)
    commands: list["Command"] = field(default_factory=list)

    @classmethod
    def parse_toml(cls, data: dict[str, Any]) -> "BotConfig":
        assignees = data.get("assignees", dict())

        config = cls(bot_user=data["bot_user"], assignees=assignees)
        commands = [
            Command.parse_toml(name, cmd_config, config)
            for name, cmd_config in data["command"].items()
        ]
        config.commands = commands

        return config


class LazyTask:
    def __init__(self, mr: ProjectMergeRequest, tasks: TaskCollection):
        self.mr = mr
        self.val: OperationsTask | None = None
        self.tasks: TaskCollection = tasks

    async def _lookup(self) -> OperationsTask | None:

        mr_num: int = cast(int, self.mr.get_id())
        task = self.tasks.get_task_by_mr(mr_num)
        if task is not None:
            return task

        task_id_str = find_task_id(self.mr)
        if task_id_str is None:
            raise ValueError(
                "Cannot find the task URL in " + self.mr.attributes["web_url"]
            )
        task_id = int(task_id_str)
        await self.tasks.load_task_id(task_id)
        task = self.tasks.get_task_by_id(task_id)
        return task

    async def get(self) -> OperationsTask | None:
        if self.val is not None:
            return self.val
        self.val = await self._lookup()
        return self.val


class Bot:
    def __init__(self, config: BotConfig, kb_project: KanboardProject) -> None:

        self.log: logging.Logger = _LOG.getChild(f"{self.__class__.__name__}")
        self.config: BotConfig = config
        self.kb_project: KanboardProject = kb_project
        self.tasks: TaskCollection = TaskCollection(kb_project)

    def _find_trigger_assign(self, mr: ProjectMergeRequest) -> TriggerInfo:
        log = self.log.getChild("_find_trigger_assign")
        trigger = TriggerInfo(TriggerType.ASSIGN)
        web_url = mr.attributes["web_url"]

        body = f"assigned to @{self.config.bot_user}"
        for note in mr.notes.list(iterator=True):
            if note.attributes["system"] and note.attributes["body"].startswith(body):
                trigger.username = note.attributes["author"]["username"]
                trigger.user_id = note.attributes["author"]["id"]
                trigger.note = note
                log.info(
                    "%s : Found assignment to bot by %s", web_url, trigger.username
                )
                return trigger

        log.warning(
            "%s : Could not figure out who last assigned this to the bot %s!",
            web_url,
            self.config.bot_user,
        )
        return trigger

    def _find_trigger_mention(
        self, mr: ProjectMergeRequest, note: ProjectMergeRequestNote
    ) -> TriggerInfo | None:
        log = self.log.getChild("_find_trigger_mention")
        body: str = note.attributes["body"].strip()

        mention = f"@{self.config.bot_user}"
        if not body.startswith(mention):
            # not a mention so not a command
            return None

        command_body = body.removeprefix(mention).strip()
        trigger = TriggerInfo(
            TriggerType.MENTION,
            username=note.attributes["author"]["username"],
            user_id=note.attributes["author"]["id"],
            command_body=command_body,
            note=note,
        )

        # Skip if we have a reaction by the bot!
        thumbs = [
            emoji.attributes["name"] == _MENTION_ACK_EMOJI
            for emoji in note.awardemojis.list(iterator=True)
        ]

        if any(thumbs):
            log.debug(
                "%s : Found bot mention by %s, already processed",
                mr.attributes["web_url"],
                trigger.username,
            )
            return None

        log.info(
            "%s : Found bot mention by %s", mr.attributes["web_url"], trigger.username
        )
        return trigger

    def _find_trigger(self, mr: ProjectMergeRequest) -> TriggerInfo | None:
        if mr.attributes["assignees"]:
            is_bot = [
                assignee_obj["username"] == self.config.bot_user
                for assignee_obj in mr.attributes["assignees"]
            ]
            if any(is_bot):
                return self._find_trigger_assign(mr)

        for note in mr.notes.list(iterator=True):
            trigger = self._find_trigger_mention(mr, note)
            if trigger is not None:
                return trigger

    async def process_mr_once(self, mr: ProjectMergeRequest):
        log = self.log.getChild("process_mr_once")
        web_url = mr.attributes["web_url"]
        trigger: TriggerInfo | None = self._find_trigger(mr)
        if trigger is None:
            return
        assert trigger

        lazy_task = LazyTask(mr, self.tasks)

        # See if we should run any command
        for cmd in self.config.commands:
            log.debug("%s : Testing command %s", web_url, cmd.name)
            # "None" means we need more info!
            if cmd.does_trigger_match(trigger) == False:
                log.debug("%s : Failed trigger")
                continue

            task = await lazy_task.get()
            if not task:
                log.warning("%s : Could not find matching operations task", web_url)
                # Cannot confidently run any actions without this, skip the whole MR
                return

            if cmd.are_conditions_satisfied(trigger, mr, task):
                log.info(
                    "%s : Running command %s: %s",
                    mr.attributes["web_url"],
                    cmd.name,
                    cmd.description,
                )

                await cmd.perform_actions(self.kb_project, trigger, mr, task)

                # Process at most one command per trigger.
                # This allows adding fall-through command at the bottom of the config,
                # in case nothing matches.
                return True


@dataclass
class Command:
    name: str
    description: str
    auto_on_assign: bool = False
    conditions_on_assign: list["ConditionConjuction"] = field(default_factory=list)
    actions: list["InteractiveAction"] = field(default_factory=list)

    @classmethod
    def parse_toml(
        cls, name: str, data: dict[str, Any], config: BotConfig
    ) -> "Command":

        conditions_on_assign: list["ConditionConjuction"] = [
            ConditionConjuction.parse_yaml(block)
            for block in data.get("condition_on_assign", list())
        ]

        actions: list[InteractiveAction] = [
            _make_action(block, config) for block in data.get("action", list())
        ]

        return Command(
            name=name,
            description=data["description"],
            auto_on_assign=data.get("auto_on_assign", False),
            conditions_on_assign=conditions_on_assign,
            actions=actions,
        )

    def does_trigger_match(self, trigger: TriggerInfo) -> bool | None:
        if trigger.trigger_type == TriggerType.MENTION:
            return self.name == trigger.command_body

        if not self.auto_on_assign:
            return False

        # OK we might run, but only "are_conditions_satisfied" (and its extra params) knows
        return None

    def are_conditions_satisfied(
        self, trigger: TriggerInfo, mr: ProjectMergeRequest, task: OperationsTask
    ):
        log = _LOG.getChild(
            f"{self.__class__.__name__}.{self.name}.are_conditions_satisfied"
        )

        match: bool | None = self.does_trigger_match(trigger)
        if match is not None:
            log.debug("Early out: trigger match gave a full result")
            # we actually got a full answer
            return match

        assert self.auto_on_assign
        # Otherwise, we are allowed to auto-run on assign subject to conditions, and this was assign.
        # Consider the conditions.
        if not self.conditions_on_assign:
            # no conditions: always do it
            log.debug("No additional conditions provided: always do it")
            return True

        for conj in self.conditions_on_assign:
            if conj.is_satisfied(mr, task):
                log.debug("Satisfied conjunction: %s", str(conj))
                return True
            log.debug("Failed conjunction: %s", str(conj))

        log.debug("Failed all conjuctions")
        return False
        # return any(conj.is_satisfied(mr, task) for conj in self.conditions_on_assign)

    async def perform_actions(
        self,
        kb_project: KanboardProject,
        trigger: TriggerInfo,
        mr: ProjectMergeRequest,
        task: OperationsTask,
    ):
        if trigger.trigger_type == TriggerType.MENTION and trigger.note:
            if _dry_run:
                logging.info("Not acknowledging due to dry run: %s", str(trigger))
            else:
                _ack_mention(trigger.note)

        for action in self.actions:
            await action.perform(kb_project, trigger, mr, task)


@dataclass
class ConditionConjuction:
    predicates: list[Callable[[ProjectMergeRequest, OperationsTask], bool]] = field(
        default_factory=list
    )

    def is_satisfied(self, mr: ProjectMergeRequest, task: OperationsTask) -> bool:
        return all(pred(mr, task) for pred in self.predicates)

    @classmethod
    def parse_yaml(cls, block: dict[str, Any]) -> "ConditionConjuction":
        log = _LOG.getChild(f"{cls.__name__}.parse_yaml")
        predicates: list[Callable[[ProjectMergeRequest, OperationsTask], bool]] = [
            _make_predicate(k, v) for k, v in block.items()
        ]
        log.debug("%d predicates combined into a conjunction", len(predicates))
        return ConditionConjuction(predicates)


class InteractiveAction(abc.ABC):
    """Interface for actions taken by the interactive bot."""

    @abc.abstractmethod
    async def perform(
        self,
        kb_project: KanboardProject,
        trigger: TriggerInfo,
        mr: ProjectMergeRequest,
        task: OperationsTask,
    ) -> None:
        raise NotImplementedError


class AssignAction(InteractiveAction):
    action_type = "assign"

    def __init__(self, data: dict[str, Any], config: BotConfig) -> None:
        super().__init__()
        self.log = _LOG.getChild(f"{self.__class__.__name__}")
        self.assign_to_self: bool = False
        self.assign_to_champion: bool = False

        who: str = data["who"]

        # Handle special assignees
        who_special: str | None = config.assignees.get(who)
        if who_special:
            self.log.info(
                "Creating assign action with special assignee: %s -> %s",
                who,
                who_special,
            )
            who = who_special

        elif who == "@self":
            self.log.info("Creating assign action that assigns to command invoker")
            self.assign_to_self = True
            who = ""

        elif who == "@champion":
            self.log.info("Creating assign action that assigns to extension champion")
            self.assign_to_champion = True
            who = ""

        if "@" in who:
            raise KeyError(
                "@ remains in assign action 'who' after processing known special assignees"
            )

        self.who: str = who

    async def perform(
        self,
        kb_project: KanboardProject,
        trigger: TriggerInfo,
        mr: ProjectMergeRequest,
        task: OperationsTask,
    ) -> None:

        if self.assign_to_self:
            if trigger.user_id is None:
                raise ValueError("Could not figure out who triggered this")

            if _dry_run:
                self.log.info(
                    "%s : Would assign to 'self' = %s (%d)",
                    mr.attributes["web_url"],
                    trigger.username,
                    trigger.user_id,
                )
                return

            self.log.info(
                "%s : Assigning to 'self' = %s (%d)",
                mr.attributes["web_url"],
                trigger.username,
                trigger.user_id,
            )
            mr.attributes["assignees"] = [trigger.user_id]
            mr.save()
            return

        if self.assign_to_champion:
            # TODO who is the champion? assign to them here!
            # this is not always clearly set anywhere.

            if _dry_run:
                self.log.info(
                    "%s : Would assign to nobody because we didn't implement finding the champion",
                    mr.attributes["web_url"],
                )
                return

            self.log.info(
                "%s : Assigning to nobody because we can't guess who the champion is",
                mr.attributes["web_url"],
            )
            mr.attributes["assignees"] = []
            mr.save()
            return

        assert not self.assign_to_champion and not self.assign_to_self

        who: str = self.who

        # OK everybody else is easy to assign to, in theory.
        assignee_ids = []
        if who:
            who_user: User = mr.manager.gitlab.users.get(who)
            user_id = who_user.get_id()

            if _dry_run:
                self.log.info(
                    "%s : Would assign to %s (%d)",
                    mr.attributes["web_url"],
                    who,
                    user_id,
                )
                return

            self.log.info(
                "%s : Assigning to  %s (%s)",
                mr.attributes["web_url"],
                who,
                str(user_id),
            )
            assignee_ids.append(user_id)
        else:
            if _dry_run:
                self.log.info(
                    "%s : Would assign to none",
                    mr.attributes["web_url"],
                )
                return

        mr.attributes["assignees"] = assignee_ids
        mr.save()


class MoveAction(InteractiveAction):
    action_type = "move"

    def __init__(self, data: dict[str, Any], config: BotConfig) -> None:
        super().__init__()
        self.log = _LOG.getChild(f"{self.__class__.__name__}")
        self.kb_project: KanboardProject
        self.kb: kanboard.Client
        self.column: TaskColumn = TaskColumn(data["column"])

    async def perform(
        self,
        kb_project: KanboardProject,
        trigger: TriggerInfo,
        mr: ProjectMergeRequest,
        task: OperationsTask,
    ):
        column_id = self.column.to_required_column_id(kb_project)
        swimlane_id = task.swimlane.to_required_swimlane_id(kb_project)

        if _dry_run:
            self.log.info("%s : Would move to column %s", str(task.url), self.column)
            return
        self.log.info("%s : Moving to column %s", str(task.url), self.column)

        await self.kb.move_task_position_async(
            project_id=self.kb_project.project_id,
            task_id=task.task_id,
            column_id=column_id,
            swimlane_id=swimlane_id,
            position=1,
        )


class MrCommentAction(InteractiveAction):
    action_type = "mr-comment"

    def __init__(self, data: dict[str, Any], config: BotConfig) -> None:
        super().__init__()
        self.log = _LOG.getChild(f"{self.__class__.__name__}")
        self.contents: str = data["contents"].strip()

    async def perform(
        self,
        kb_project: KanboardProject,
        trigger: TriggerInfo,
        mr: ProjectMergeRequest,
        task: OperationsTask,
    ):
        if _dry_run:
            self.log.info(
                "%s : Would post comment %s", mr.attributes["web_url"], self.contents
            )
            return
        mr.notes.create({"body": self.contents})


class TagsAction(InteractiveAction):
    """Tags for task."""

    action_type = "tags"

    def __init__(self, data: dict[str, Any], config: BotConfig) -> None:
        super().__init__()
        self.log = _LOG.getChild(f"{self.__class__.__name__}")
        self.add: list[str] = data.get("add", list())
        self.remove: list[str] = data.get("remove", list())

    async def perform(
        self,
        kb_project: KanboardProject,
        trigger: TriggerInfo,
        mr: ProjectMergeRequest,
        task: OperationsTask,
    ):
        if _dry_run:
            self.log.info(
                "%s : Would add task tags %s, remove tags %s",
                str(task.url),
                str(self.add),
                str(self.remove),
            )
            return
        raise NotImplementedError


class MrLabelAction(InteractiveAction):
    """labels for MR."""

    action_type = "mr-label"

    def __init__(self, data: dict[str, Any], config: BotConfig) -> None:
        super().__init__()
        self.log = _LOG.getChild(f"{self.__class__.__name__}")
        self.add: list[str] = data.get("add", list())
        self.remove: list[str] = data.get("remove", list())

    async def perform(
        self,
        kb_project: KanboardProject,
        trigger: TriggerInfo,
        mr: ProjectMergeRequest,
        task: OperationsTask,
    ):
        if _dry_run:
            self.log.info(
                "%s : MR labels: would add %s, remove %s",
                mr.attributes["web_url"],
                str(self.add),
                str(self.remove),
            )
            return
        raise NotImplementedError


class CompleteSubtasksAction(InteractiveAction):
    """Mark subtasks on Kanboard as complete."""

    action_type = "complete-subtasks"

    def __init__(self, data: dict[str, Any], config: BotConfig) -> None:
        super().__init__()
        self.log = _LOG.getChild(f"{self.__class__.__name__}")
        self.subtasks: list[str] = data.get("subtasks", list())

    async def perform(
        self,
        kb_project: KanboardProject,
        trigger: TriggerInfo,
        mr: ProjectMergeRequest,
        task: OperationsTask,
    ):
        if _dry_run:
            self.log.info(
                "%s : Would mark these subtasks as completed: %s",
                str(task.url),
                str(self.subtasks),
            )
            return
        raise NotImplementedError


ActionFactory: TypeAlias = Callable[[dict[str, Any], BotConfig], InteractiveAction]

_ACTION_TYPES: dict[str, ActionFactory] = {
    c.action_type: c
    for c in [
        MoveAction,
        AssignAction,
        MrCommentAction,
        TagsAction,
        MrLabelAction,
        CompleteSubtasksAction,
    ]
}


def _make_action(data: dict[str, Any], config: BotConfig) -> InteractiveAction:
    action_type = data["type"]
    action_class = _ACTION_TYPES.get(action_type)
    if not action_class:
        raise ValueError("Unknown action type: " + action_type)
    return action_class(data, config)


Predicate: TypeAlias = Callable[[ProjectMergeRequest, OperationsTask], bool]


def _make_predicate(key: str, val: Any) -> Predicate:
    log = _LOG.getChild(f"_make_predicate")

    if key == "column":
        col = TaskColumn(val)
        log.debug("Returning predicate to compare column to %s", str(col))
        return _make_is_column(col)

    if key == "blocking_discussions_resolved":
        log.debug(
            "Returning predicate to compare blocking_discussions_resolved to %s",
            str(val),
        )
        return _make_is_resolved(val)

    raise ValueError("Unrecognized predicate key: " + key)


def _make_is_column(desired_column: TaskColumn) -> Predicate:
    def is_column(mr: ProjectMergeRequest, task: OperationsTask):
        return task.column == desired_column

    return is_column


def _make_is_resolved(desired_resolved_state: bool) -> Predicate:
    def is_resolved(mr: ProjectMergeRequest, task: OperationsTask):
        return (
            mr.attributes.get("blocking_discussions_resolved") == desired_resolved_state
        )

    return is_resolved


def get_config_data() -> BotConfig:
    """Load the bundled bot configuration."""
    data = (
        importlib.resources.files("openxr_ops.kb_ops")
        .joinpath("commands.toml")
        .read_text(encoding="utf-8")
    )
    parsed = tomllib.loads(data)
    return BotConfig.parse_toml(parsed)


if __name__ == "__main__":

    from dotenv import load_dotenv

    load_dotenv()

    import argparse

    parser = argparse.ArgumentParser(add_help=True)

    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Do not actually make any changes",
        default=False,
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Higher log level",
        default=False,
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.dry_run:
        _dry_run = True

    oxr_gitlab = OpenXRGitlab.create()

    config = get_config_data()
    import pprint

    pprint.pprint(config)

    async def wrapper():
        kb_project: KanboardProject = await load_kb_project()

        # not loading the tasks right away

        bot = Bot(config, kb_project)

        # TODO do more than handle just a single hard-coded MR here.
        # process web hooks? or worst case iterate all the extension MRs.
        mr = oxr_gitlab.main_proj.mergerequests.get(3104)
        await bot.process_mr_once(mr)

    asyncio.run(wrapper())
