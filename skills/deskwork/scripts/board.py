"""Projects v2, which is GraphQL only, and optional.

deskwork works from labels alone. A board is an extra: with `project` set in
the config, capture also puts each new issue on it with Status set to Triage.

The project is always addressed by node id. Titles are not unique, a project
need not be linked to the repository, and --add-project silently adds to one
of two same-named boards. deskwork creates no fields: the one thing it adds
is the Triage option on the built-in Status field, and it keeps every existing
option's id when it does, so no item loses its status.
"""
import gh
import ids

TRIAGE_COLOUR = "GRAY"
TRIAGE_DESCRIPTION = "Filed by an agent and not yet reviewed"


class MissingScope(Exception):
    """The token cannot see Projects. Say so, rather than leaking a GraphQL error."""


class NotConfirmed(Exception):
    """A board write reported success and does not read back as asked."""


def _graphql(query, **variables):
    try:
        return gh.graphql(query, **variables)
    except gh.GhError as error:
        if "read:project" in str(error) or "required scopes" in str(error):
            raise MissingScope(
                "Projects v2 needs the project scope, which this token does not "
                "have. Run: gh auth refresh -s project"
            ) from error
        raise


_FIELDS = """
query DeskworkBoardFields($project: ID!) {
  node(id: $project) {
    ... on ProjectV2 {
      title
      fields(first: 50) {
        totalCount
        nodes {
          ... on ProjectV2SingleSelectField { id name options { id name color description } }
          ... on ProjectV2Field { id name }
        }
      }
    }
  }
}"""


def fields(project_id):
    """{name: field} for every field on the board. Single-selects carry options."""
    data = _graphql(_FIELDS, project=project_id)
    node = data.get("node") or {}
    if "fields" not in node:
        raise gh.GhError(f"{project_id} is not a Projects v2 board this token can see")
    return {f["name"]: f for f in node["fields"]["nodes"] if f}


def title(project_id):
    return (_graphql(_FIELDS, project=project_id).get("node") or {}).get("title", project_id)


_ITEMS = """
query DeskworkBoardItems($project: ID!, $after: String) {
  node(id: $project) {
    ... on ProjectV2 {
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          content { ... on Issue { number repository { nameWithOwner } } }
          fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
        }
      }
    }
  }
}"""


def items(project_id):
    """Every issue on the board, however many pages: [(Ref, ItemId, status)]."""
    found, after = [], None
    while True:
        data = _graphql(_ITEMS, project=project_id, after=after)
        page = data["node"]["items"]
        for node in page["nodes"]:
            content = node.get("content") or {}
            if "number" not in content:
                continue  # a draft item or a pull request
            owner, _, name = content["repository"]["nameWithOwner"].partition("/")
            status = (node.get("fieldValueByName") or {}).get("name")
            found.append((ids.Ref(owner, name, ids.IssueNumber(content["number"])),
                          ids.ItemId(node["id"]), status))
        if not page["pageInfo"]["hasNextPage"]:
            return found
        after = page["pageInfo"]["endCursor"]


_ADD = """
mutation DeskworkAddItem($project: ID!, $content: ID!) {
  addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } }
}"""


def add_item(project_id, content_id):
    """Put an issue on the board. Returns the item id, which set_field needs."""
    ids.require_node_id(content_id)
    data = _graphql(_ADD, project=project_id, content=str(content_id))
    return ids.ItemId(data["addProjectV2ItemById"]["item"]["id"])


_SET = """
mutation DeskworkSetStatus($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $project, itemId: $item, fieldId: $field,
    value: {singleSelectOptionId: $option}
  }) { projectV2Item { id } }
}"""

_STATUS = """
query DeskworkItemStatus($item: ID!) {
  node(id: $item) {
    ... on ProjectV2Item {
      fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
    }
  }
}"""


def status(item_id):
    ids.require_item_id(item_id)
    node = _graphql(_STATUS, item=str(item_id)).get("node") or {}
    return (node.get("fieldValueByName") or {}).get("name")


def set_field(project_id, item_id, field_id, option_id):
    """Set a single-select field on a board item. Takes the item id, never the issue's."""
    ids.require_item_id(item_id)
    _graphql(_SET, project=project_id, item=str(item_id), field=field_id, option=option_id)


def set_status(project_id, item_id, wanted):
    """Set Status to the option called wanted, then read it back."""
    ids.require_item_id(item_id)
    field = fields(project_id).get("Status")
    option = next((o for o in (field or {}).get("options", []) if o["name"] == wanted), None)
    if option is None:
        raise NotConfirmed(
            f"the board {title(project_id)} ({project_id}) has no {wanted!r} option on "
            f"Status. Run init to add it."
        )
    set_field(project_id, item_id, field["id"], option["id"])
    found = status(item_id)
    if found != wanted:
        raise NotConfirmed(f"Status on {item_id} reads {found!r}, not {wanted!r}")


_ADD_OPTION = """
mutation DeskworkAddOption($field: ID!, $options: [ProjectV2SingleSelectFieldOptionInput!]!) {
  updateProjectV2Field(input: {fieldId: $field, singleSelectOptions: $options}) {
    projectV2Field { ... on ProjectV2SingleSelectField { id options { id name } } }
  }
}"""


def ensure_status_option(project_id, name):
    """Add the option called name to Status if it is missing. Returns True if added.

    GitHub replaces the whole option list on update, so every existing option
    is sent back with its id, colour and description, read immediately before.
    Afterwards every one of those ids must still be there, and the new option
    too, or the write is reported as not confirmed.
    """
    field = fields(project_id).get("Status")
    if field is None or "options" not in field:
        raise NotConfirmed(f"the board {project_id} has no single-select Status field")
    existing = field["options"]
    if any(o["name"] == name for o in existing):
        return False
    options = [
        {"id": o["id"], "name": o["name"], "color": o["color"], "description": o.get("description") or ""}
        for o in existing
    ]
    options.append({"name": name, "color": TRIAGE_COLOUR, "description": TRIAGE_DESCRIPTION})
    _graphql(_ADD_OPTION, field=field["id"], options=options)
    after = fields(project_id).get("Status") or {}
    after_ids = {o["id"] for o in after.get("options", [])}
    lost = [o["name"] for o in existing if o["id"] not in after_ids]
    if lost or not any(o["name"] == name for o in after.get("options", [])):
        raise NotConfirmed(
            f"Status on {project_id} did not read back as asked. "
            f"Missing now: {lost or [name]}. Check the board by hand."
        )
    return True
