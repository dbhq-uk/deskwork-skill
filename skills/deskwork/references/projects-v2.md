# Projects v2

Projects v2 is GraphQL only - there is no REST equivalent. All interactions flow through four entry points: `board.fields()`, `board.items()`, `board.add_item()` and `board.set_field()`. Each wraps a GraphQL call and translates authentication errors into `MissingScope`.

## Identifiers

One GitHub issue carries three different identifiers and none of them is interchangeable:

| Identifier | Looks like | Used by |
|---|---|---|
| Issue number | `144` | humans, URLs, the REST path |
| Database id, `IssueId(int)` | `3527190001` | the dependencies API `issue_id` field |
| GraphQL node id, `NodeId(str)` | `"I_kwDOAbc123"` | every Projects v2 mutation |

Always use the right type for the right call:
- REST API (issues, dependencies) takes an issue number or database id
- Projects v2 mutations take GraphQL node id

The type system prevents confusion: `IssueId` and `NodeId` are distinct types, and passing one where the other belongs raises `TypeError`. Fetch the right identifier with `ids.resolve()` (for database id) or `ids.node_id()` (for GraphQL node id).

## Projects must be addressed by node id

A project is always addressed by node id, never by title. Titles are not unique - a project need not even be linked to the repository. If you address a project by title, `--add-project` silently adds to one of two same-named boards. The project's own node id - returned by `projects list` or a Projects v2 query - is the only unambiguous address.

## Authentication: the project scope

Projects v2 mutations require the `project` scope. This is separate from the `repo` scope and must be granted explicitly:

```bash
gh auth refresh -s project
```

Check the current token's scopes with `gh auth status`.

If a mutation fails because the scope is missing, `board` raises `MissingScope` with the command to fix it. The error message names the fix (`gh auth refresh -s project`) rather than leaking the GraphQL error.

## Mutations

### add_item

Add an issue to a project:

```python
import ids
import board

ref = ids.Ref("owner", "repo", ids.IssueNumber(144))
node = ids.node_id(ref)
item_id = board.add_item("PVT_kwDOABCD1234", node)
```

The issue must be passed as a GraphQL node id. The project must be passed as a GraphQL node id. Returns the item id.

### set_field

Set a single-select field on a project item:

```python
board.set_field("PVT_kwDOABCD1234", item_id, field_id, option_id)
```

Takes four node/field ids returned by `fields()` and `items()`. Returns nothing.

## Queries

### fields

List the fields (columns) in a project:

```python
field_dict = board.fields("PVT_kwDOABCD1234")
```

Returns a dict keyed by field name, with each entry holding the field's id, name, and options (for single-select fields). The key is the field's display name; the id is a GraphQL node id for use in `set_field()`.

### items

List the issues in a project:

```python
item_list = board.items("PVT_kwDOABCD1234")
```

Returns a list of items, each holding the item's id, the issue's number/repository/state, and the field values on that item. Filtered to exclude draft items (which have no `content`).
